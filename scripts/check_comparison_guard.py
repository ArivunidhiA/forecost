"""Fail when compare strictness changes without matching test or golden-snapshot changes.

Usage: python scripts/check_comparison_guard.py BASE_REF
Compares HEAD with BASE_REF (e.g. origin/main). If forecost/comparison.py changed, at least one
of tests/test_comparison.py, tests/test_comparison_golden.py or tests/golden/compare_v1.json must
change too, so fixtures and the decision snapshot move together with the code.
"""

from __future__ import annotations

import subprocess
import sys

GUARDED = "forecost/comparison.py"
COMPANIONS = {
    "tests/test_comparison.py",
    "tests/test_comparison_golden.py",
    "tests/golden/compare_v1.json",
}


def changed_files(base: str) -> set[str]:
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "diff", "--name-only", f"{base}...HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    changed = changed_files(argv[1])
    if GUARDED in changed and not (changed & COMPANIONS):
        print(
            f"FAIL: {GUARDED} changed but none of {sorted(COMPANIONS)} did. "
            "Update fixtures/snapshot (UPDATE_COMPARISON_GOLDEN=1) with the code change."
        )
        return 1
    print("comparison guard ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
