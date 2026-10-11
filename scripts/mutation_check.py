"""Small, fast AST mutation tester for the money- and privacy-critical modules.

Usage: python scripts/mutation_check.py forecost/pricing.py --tests tests/test_pricing.py ... \
           [--jobs 4] [--timeout 90] [--max N] [--report out.json]

One mutant at a time is written into a private copy of the package and the given tests run
against it (PYTHONPATH precedence). A mutant is KILLED when the tests fail/time out, SURVIVED when
they pass. Operators: comparison flips, boundary shifts, arithmetic swaps, boolean inversion,
numeric constant perturbation, `and`/`or` swap, and `not` removal.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_CMP = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
_BIN = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.Mult,
}


@dataclass
class Mutant:
    index: int
    line: int
    operator: str
    status: str = "pending"


def _sites(tree: ast.AST) -> list[tuple[str, ast.AST, int]]:
    out: list[tuple[str, ast.AST, int]] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in _CMP:
                    out.append((f"cmp:{i}", node, line))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            out.append(("bin", node, line))
        elif isinstance(node, ast.BoolOp):
            out.append(("bool", node, line))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            out.append(("not", node, line))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            out.append(("const", node, line))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            out.append(("boolconst", node, line))
    return out


def _apply(tree: ast.Module, index: int) -> tuple[ast.Module, str, int]:
    clone = copy.deepcopy(tree)
    kind, node, line = _sites(clone)[index]
    if kind.startswith("cmp"):
        i = int(kind.split(":")[1])
        node.ops[i] = _CMP[type(node.ops[i])]()  # type: ignore[attr-defined]
    elif kind == "bin":
        node.op = _BIN[type(node.op)]()  # type: ignore[attr-defined]
    elif kind == "bool":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()  # type: ignore[attr-defined]
    elif kind == "not":
        node.__class__ = ast.UnaryOp
        node.op = ast.UAdd()  # type: ignore[attr-defined]
    elif kind == "const":
        value = node.value  # type: ignore[attr-defined]
        node.value = value + 1 if value != 1 else 2  # type: ignore[attr-defined]
    elif kind == "boolconst":
        node.value = not node.value  # type: ignore[attr-defined]
    ast.fix_missing_locations(clone)
    return clone, kind, line


def _run(args: argparse.Namespace, target: Path, tree: ast.Module, index: int) -> Mutant:
    mutated, kind, line = _apply(tree, index)
    work = Path(tempfile.mkdtemp(prefix="mut-"))
    try:
        shutil.copytree(
            ROOT,
            work / "r",
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv*",
                "mutants",
                "__pycache__",
                ".ruff_cache",
                ".hypothesis",
                ".mypy_cache",
                "*.egg-info",
                "dist",
                "build",
                ".benchmarks",
                "coverage.xml",
            ),
        )
        repo = work / "r"
        (repo / target.relative_to(ROOT)).write_text(ast.unparse(mutated), encoding="utf-8")
        env = {
            **os.environ,
            "PYTHONPATH": str(repo),
            "FORECOST_HOME": str(work / "home"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-x",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--benchmark-disable",
                    "-p",
                    "no:randomly",
                    *args.tests,
                ],
                cwd=repo,
                env=env,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
            status = "survived" if done.returncode == 0 else "killed"
        except subprocess.TimeoutExpired:
            status = "killed"  # a mutant that hangs is detected by the suite
        return Mutant(index, line, kind, status)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("module")
    parser.add_argument("--tests", nargs="+", required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--max", type=int, default=0)
    parser.add_argument("--lines", default="", help="START-END limit")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    target = (ROOT / args.module).resolve()
    tree = ast.parse(target.read_text(encoding="utf-8"))
    # Baseline must be green, otherwise every mutant would look 'killed'.
    base = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "-x",
            "-q",
            "-p",
            "no:cacheprovider",
            "--benchmark-disable",
            *args.tests,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=600,
    )
    if base.returncode != 0:
        sys.stderr.write("baseline tests failing; refusing to run\n")
        sys.stderr.write((base.stdout + base.stderr).decode("utf-8", "replace")[-1500:])
        return 2
    indexes = list(range(len(_sites(tree))))
    if args.lines:
        lo, hi = (int(x) for x in args.lines.split("-"))
        indexes = [i for i in indexes if lo <= _sites(tree)[i][2] <= hi]
    if args.max:
        indexes = indexes[: args.max]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda i: _run(args, target, tree, i), indexes))
    killed = sum(r.status == "killed" for r in results)
    survived = [r for r in results if r.status == "survived"]
    sys.stdout.write(
        f"{args.module}: {killed}/{len(results)} killed "
        f"({100 * killed / max(1, len(results)):.1f}%); {len(survived)} survived\n"
    )
    src = target.read_text(encoding="utf-8").splitlines()
    for r in sorted(survived, key=lambda m: m.line):
        sys.stdout.write(
            f"  SURVIVED line {r.line} [{r.operator}]: {src[r.line - 1].strip()[:110]}\n"
        )
    if args.report:
        Path(args.report).write_text(json.dumps([asdict(r) for r in results], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
