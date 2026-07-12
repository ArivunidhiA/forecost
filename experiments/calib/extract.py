"""Extract prompt-turn records from local Claude Code JSONL transcripts.

Implements the extraction protocol from round3-estimation.md §6.2 and the label
columns added by round5-risk.md §5.1. Reads ~/.claude/projects/**/*.jsonl (main
sessions) plus sibling subagents/agent-*.jsonl files (subagent usage, joined by
promptId), and writes one row per prompt-turn to a local SQLite database.

Privacy: no prompt text, completion text, or raw file paths are persisted. File
paths are reduced to counts and a stable hash of the sorted path list. Prompt
text is used in-process only to compute scalar features, never written out
(matches the content-free ledger invariant in BASEMENT.md L5).

Usage:
    python3 extract.py [--claude-dir ~/.claude/projects] [--out turns.db]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from forecost.pricing import calculate_cost  # noqa: E402

SCOPE_MAXIMIZER_RE = re.compile(
    r"\b(all|every|entire|comprehensive|throughout|across the codebase)\b", re.IGNORECASE
)
FILE_MENTION_RE = re.compile(
    r"[\w./-]+\.(?:py|ts|tsx|js|jsx|md|json|toml|yaml|yml|sql|go|rs|java|rb|sh)\b"
)
TEST_CMD_RE = re.compile(r"\b(pytest|npm test|yarn test|go test|cargo test|jest|vitest)\b")
TEST_PASS_RE = re.compile(r"\b(\d+ passed|PASS|OK\b|all tests passed)\b", re.IGNORECASE)
TEST_FAIL_RE = re.compile(r"\b(\d+ failed|FAIL\b|AssertionError|Error:)\b")
EXIT_CODE_RE = re.compile(r"[Ee]xit code (\d+)")
SENSITIVE_PATH_RE = re.compile(
    r"(auth|session|migrat|payment|billing|\.env|secret|credential|ci\.ya?ml|"
    r"\.github/workflows)",
    re.IGNORECASE,
)

TASK_CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("fanout-batch", re.compile(r"\b(parallel|subagents?|swarm|spawn|fan[- ]?out)\b", re.I)),
    ("test-work", re.compile(r"\b(test|pytest|spec|coverage)\b", re.I)),
    ("bugfix-debug", re.compile(r"\b(fix|bug|debug|issue|broken|crash|error)\b", re.I)),
    ("refactor", re.compile(r"\b(refactor|restructure|clean ?up|simplify)\b", re.I)),
    ("docs-writing", re.compile(r"\b(docs?|documentation|readme|comment)\b", re.I)),
    ("config-devops", re.compile(r"\b(ci|cd|deploy|docker|config|pipeline|build)\b", re.I)),
    ("repo-research", re.compile(r"\b(explain|find|review|understand|what does)\b", re.I)),
    ("web-research", re.compile(r"\b(research|search the web|look up)\b", re.I)),
    ("data-scripting", re.compile(r"\b(script|analyze|extract|parse|csv|dataset)\b", re.I)),
    ("continuation-misc", re.compile(r"^/|^\s*(yes|ok|continue|thanks)\s*$", re.I)),
]


def classify_category(prompt: str) -> str:
    for label, pattern in TASK_CATEGORY_RULES:
        if pattern.search(prompt):
            return label
    if re.search(r"\b(add|implement|build|create|write)\b", prompt, re.I):
        return "feature-build"
    return "quick-edit"


@dataclass
class TurnAccumulator:
    session_id: str
    prompt_id: str
    project_dir: str
    ts_start: str
    prompt_text: str = ""
    ts_end: str = ""
    model_mix: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    files_touched: set[str] = field(default_factory=set)
    error_result_count: int = 0
    total_tool_results: int = 0
    consec_errors: int = 0
    max_consec_errors: int = 0
    tail_errors_last5: list[bool] = field(default_factory=list)
    bash_texts: list[str] = field(default_factory=list)
    test_ran: bool = False
    compaction_events: int = 0
    api_errors: int = 0
    interrupted: bool = False


def _is_real_user_prompt(rec: dict) -> bool:
    if rec.get("type") != "user":
        return False
    if rec.get("isMeta"):
        return False
    if not rec.get("promptId"):
        return False
    msg = rec.get("message") or {}
    content = msg.get("content")
    return isinstance(content, str) and content.strip() != ""


def _path_hash(paths: set[str]) -> str:
    joined = "|".join(sorted(paths))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def _extract_features(prompt: str) -> dict:
    return {
        "prompt_chars": len(prompt),
        "prompt_words": len(prompt.split()),
        "n_file_mentions": len(FILE_MENTION_RE.findall(prompt)),
        "n_bullets": len(re.findall(r"^\s*[-*]|\d+\.", prompt, re.MULTILINE)),
        "has_scope_maximizer": bool(SCOPE_MAXIMIZER_RE.search(prompt)),
        "has_sensitive_path_mention": bool(SENSITIVE_PATH_RE.search(prompt)),
        "is_question": prompt.strip().endswith("?"),
    }


def _flush_turn(turn: TurnAccumulator, conn: sqlite3.Connection) -> None:
    if turn.model_calls == 0 and turn.tool_calls == 0:
        # Nothing observable happened after this prompt (e.g. trailing prompt with
        # no response captured yet); skip rather than record a zero-cost phantom turn.
        return
    dominant_model = max(turn.model_mix, key=turn.model_mix.get) if turn.model_mix else "unknown"
    cost = calculate_cost(
        dominant_model, turn.tokens_in, turn.tokens_out, turn.cache_read, turn.cache_write
    )
    try:
        t0 = datetime.fromisoformat(turn.ts_start.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat((turn.ts_end or turn.ts_start).replace("Z", "+00:00"))
        duration_s = max(0.0, (t1 - t0).total_seconds())
    except (ValueError, TypeError):
        duration_s = 0.0
    duration_s = min(duration_s, 5 * 3600)  # idle-cap at 5h (round3-estimation §6.2)

    tail_error_flag = any(turn.tail_errors_last5[-5:]) if turn.tail_errors_last5 else False
    test_red_green = False
    test_never_green = False
    if turn.test_ran:
        joined = "\n".join(turn.bash_texts)
        saw_fail = bool(TEST_FAIL_RE.search(joined))
        saw_pass = bool(TEST_PASS_RE.search(joined))
        test_red_green = saw_fail and saw_pass
        test_never_green = saw_fail and not saw_pass

    weak_outcome = "ambiguous"
    if test_red_green:
        weak_outcome = "ok"
    elif test_never_green or (tail_error_flag and turn.max_consec_errors >= 3):
        weak_outcome = "fail"
    elif turn.error_result_count == 0:
        weak_outcome = "ok"

    features = _extract_features(turn.prompt_text)
    category = classify_category(turn.prompt_text)

    conn.execute(
        """
        INSERT OR IGNORE INTO turns (
            session_id, prompt_id, project_dir, ts_start, ts_end, category,
            prompt_features, model_mix, tokens_in, tokens_out, cache_read, cache_write,
            cost_usd_api_equiv, duration_s, model_calls, tool_calls, files_touched,
            files_hash, error_result_count, max_consec_errors, tail_error_flag,
            test_ran, test_red_green, test_never_green, compaction_events, api_errors,
            interrupted_flag, weak_outcome
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            turn.session_id,
            turn.prompt_id,
            turn.project_dir,
            turn.ts_start,
            turn.ts_end,
            category,
            json.dumps(features),
            json.dumps(dict(turn.model_mix)),
            turn.tokens_in,
            turn.tokens_out,
            turn.cache_read,
            turn.cache_write,
            cost,
            duration_s,
            turn.model_calls,
            turn.tool_calls,
            len(turn.files_touched),
            _path_hash(turn.files_touched),
            turn.error_result_count,
            turn.max_consec_errors,
            int(tail_error_flag),
            int(turn.test_ran),
            int(test_red_green),
            int(test_never_green),
            turn.compaction_events,
            turn.api_errors,
            int(turn.interrupted),
            weak_outcome,
        ),
    )


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            prompt_id TEXT,
            project_dir TEXT NOT NULL,
            ts_start TEXT NOT NULL,
            ts_end TEXT NOT NULL,
            category TEXT NOT NULL,
            prompt_features TEXT NOT NULL,
            model_mix TEXT NOT NULL,
            tokens_in INTEGER, tokens_out INTEGER,
            cache_read INTEGER, cache_write INTEGER,
            cost_usd_api_equiv REAL,
            duration_s REAL,
            model_calls INTEGER, tool_calls INTEGER,
            files_touched INTEGER,
            files_hash TEXT,
            error_result_count INTEGER,
            max_consec_errors INTEGER,
            tail_error_flag INTEGER,
            test_ran INTEGER,
            test_red_green INTEGER,
            test_never_green INTEGER,
            compaction_events INTEGER,
            api_errors INTEGER,
            interrupted_flag INTEGER,
            weak_outcome TEXT,
            UNIQUE(session_id, prompt_id)
        );
        """
    )


def _process_file(
    path: Path, conn: sqlite3.Connection, project_dir_override: str | None = None
) -> int:
    turn: TurnAccumulator | None = None
    count = 0
    project_dir = project_dir_override or ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue

        rtype = rec.get("type")
        cwd = rec.get("cwd")
        if cwd:
            project_dir = cwd
        ts = rec.get("timestamp", "")

        if _is_real_user_prompt(rec):
            if turn is not None:
                _flush_turn(turn, conn)
                count += 1
            msg = rec.get("message") or {}
            turn = TurnAccumulator(
                session_id=rec.get("sessionId", path.stem),
                prompt_id=rec.get("promptId", ""),
                project_dir=project_dir,
                ts_start=ts,
                prompt_text=str(msg.get("content", ""))[:4000],
            )
            turn.ts_end = ts
            continue

        if turn is None:
            continue
        turn.ts_end = ts or turn.ts_end

        if rtype == "assistant":
            msg = rec.get("message") or {}
            model = msg.get("model", "unknown")
            if model != "<synthetic>":
                turn.model_mix[model] += 1
                turn.model_calls += 1
            usage = msg.get("usage") or {}
            turn.tokens_in += usage.get("input_tokens", 0) or 0
            turn.tokens_out += usage.get("output_tokens", 0) or 0
            turn.cache_read += usage.get("cache_read_input_tokens", 0) or 0
            turn.cache_write += usage.get("cache_creation_input_tokens", 0) or 0
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        turn.tool_calls += 1
                        tool_input = block.get("input") or {}
                        fp = tool_input.get("file_path")
                        if fp and block.get("name") in ("Edit", "Write", "NotebookEdit"):
                            turn.files_touched.add(fp)
                        if block.get("name") == "Bash":
                            cmd = str(tool_input.get("command", ""))
                            if TEST_CMD_RE.search(cmd):
                                turn.test_ran = True

        elif rtype == "user":
            msg = rec.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    turn.total_tool_results += 1
                    is_error = bool(block.get("is_error"))
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_text = " ".join(
                            b.get("text", "") for b in result_content if isinstance(b, dict)
                        )
                    else:
                        result_text = str(result_content)
                    if is_error:
                        turn.error_result_count += 1
                        turn.consec_errors += 1
                        turn.max_consec_errors = max(
                            turn.max_consec_errors, turn.consec_errors
                        )
                    else:
                        turn.consec_errors = 0
                    turn.tail_errors_last5.append(is_error)
                    if turn.test_ran:
                        turn.bash_texts.append(result_text[:2000])
                    tur = rec.get("toolUseResult")
                    if isinstance(tur, dict) and tur.get("interrupted"):
                        turn.interrupted = True

        elif rtype == "system":
            subtype = rec.get("subtype")
            if subtype == "compact_boundary":
                turn.compaction_events += 1
            elif subtype == "api_error":
                turn.api_errors += 1

    if turn is not None:
        _flush_turn(turn, conn)
        count += 1
    return count


def _join_subagents(session_file: Path, conn: sqlite3.Connection) -> int:
    """Roll subagent token usage into the parent turn matched by promptId.

    Subagent transcripts live at <project-dir>/<session-uuid>/subagents/agent-*.jsonl
    — a directory named after the session file's stem, not a sibling of the file.
    """
    subagent_dir = session_file.parent / session_file.stem / "subagents"
    if not subagent_dir.is_dir():
        return 0
    joined = 0
    for agent_file in subagent_dir.glob("agent-*.jsonl"):
        try:
            lines = agent_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        prompt_id = None
        extra_in = extra_out = extra_cache_r = extra_cache_w = 0
        extra_tool_calls = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("promptId") and prompt_id is None:
                prompt_id = rec.get("promptId")
            if rec.get("type") == "assistant":
                usage = (rec.get("message") or {}).get("usage") or {}
                extra_in += usage.get("input_tokens", 0) or 0
                extra_out += usage.get("output_tokens", 0) or 0
                extra_cache_r += usage.get("cache_read_input_tokens", 0) or 0
                extra_cache_w += usage.get("cache_creation_input_tokens", 0) or 0
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, list):
                    extra_tool_calls += sum(
                        1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
                    )
        if prompt_id is None:
            continue
        row = conn.execute(
            "SELECT id, tokens_in, tokens_out, cache_read, cache_write, tool_calls, "
            "cost_usd_api_equiv, model_mix FROM turns WHERE prompt_id = ?",
            (prompt_id,),
        ).fetchone()
        if row is None:
            continue
        (tid, tin, tout, cr, cw, tc, old_cost, model_mix_json) = row
        model_mix = json.loads(model_mix_json) if model_mix_json else {}
        dominant_model = max(model_mix, key=model_mix.get) if model_mix else "unknown"
        new_in = tin + extra_in
        new_out = tout + extra_out
        new_cr = cr + extra_cache_r
        new_cw = cw + extra_cache_w
        new_cost = calculate_cost(dominant_model, new_in, new_out, new_cr, new_cw)
        conn.execute(
            "UPDATE turns SET tokens_in=?, tokens_out=?, cache_read=?, cache_write=?, "
            "tool_calls=?, cost_usd_api_equiv=? WHERE id=?",
            (new_in, new_out, new_cr, new_cw, tc + extra_tool_calls, new_cost, tid),
        )
        joined += 1
    return joined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--claude-dir", default=str(Path.home() / ".claude" / "projects")
    )
    parser.add_argument("--out", default=str(Path(__file__).parent / "turns.db"))
    parser.add_argument("--project-filter", default=None, help="Substring filter on project dir")
    args = parser.parse_args()

    claude_dir = Path(args.claude_dir)
    out_path = Path(args.out)
    if out_path.exists():
        out_path.unlink()

    conn = sqlite3.connect(out_path)
    _init_db(conn)

    session_files = [
        p
        for p in claude_dir.rglob("*.jsonl")
        if "/subagents/" not in str(p)
    ]
    total_turns = 0
    processed_files = 0
    for sf in sorted(session_files):
        if args.project_filter and args.project_filter not in str(sf):
            continue
        n = _process_file(sf, conn)
        total_turns += n
        processed_files += 1
        conn.commit()

    joined = 0
    for sf in sorted(session_files):
        if args.project_filter and args.project_filter not in str(sf):
            continue
        joined += _join_subagents(sf, conn)
    conn.commit()

    n_turns = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    n_categories = conn.execute("SELECT COUNT(DISTINCT category) FROM turns").fetchone()[0]
    print(f"Processed {processed_files} session files -> {n_turns} turns "
          f"({n_categories} categories); subagent-joins applied: {joined}")
    print(f"Wrote {out_path}")
    conn.close()


if __name__ == "__main__":
    main()
