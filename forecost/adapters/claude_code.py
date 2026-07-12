"""Claude Code JSONL transcript adapter — the beachhead ingestion surface.

Reads ~/.claude/projects/**/*.jsonl (main session files; subagent files under
<session-uuid>/subagents/agent-*.jsonl are read too, tagged isSidechain).
Byte-offset resumable per file via IngestStateStore. Idempotent by construction
(event_uid dedup at the ledger write layer). Tolerant: a corrupt line is
skipped and logged, never halts ingestion.

No dollar field exists in current Claude Code transcripts — cost is always
computed downstream from tokens x pricing (LedgerSink's job), never read here.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from forecost.adapters.base import IngestStateStore, LedgerSink, PullAdapter, UsageEvent
from forecost.core.errlog import log_error


def _default_claude_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _parse_timestamp(ts_raw: str | None) -> datetime | None:
    if not ts_raw:
        return None
    try:
        return datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def _extract_usage(rec: dict) -> tuple[dict, str] | None:
    """Return (usage_dict, model) if this record is a billable assistant
    message, else None (no usage, missing model, or a synthetic placeholder)."""
    msg = rec.get("message") or {}
    usage = msg.get("usage")
    model = msg.get("model")
    if not usage or not model or model == "<synthetic>":
        return None
    return usage, model


def _build_event(
    rec: dict, usage: dict, model: str, source: str, ts, current_prompt_id: str | None
) -> UsageEvent:
    request_id = rec.get("requestId") or rec.get("uuid", "")
    event_uid = f"cc:{request_id}:{rec.get('uuid', '')}"
    return UsageEvent(
        event_uid=event_uid,
        ts=ts,
        source=source,
        model=model,
        provider="anthropic",
        session_uid=rec.get("sessionId"),
        run_id=current_prompt_id,
        agent="claude-code",
        workspace_path=rec.get("cwd"),
        tokens_in=usage.get("input_tokens", 0) or 0,
        tokens_out=usage.get("output_tokens", 0) or 0,
        tokens_cache_read=usage.get("cache_read_input_tokens", 0) or 0,
        tokens_cache_write=usage.get("cache_creation_input_tokens", 0) or 0,
        metadata={
            "is_sidechain": bool(rec.get("isSidechain")),
            "entrypoint": rec.get("entrypoint"),
        },
    )


def _record_to_event(rec: dict, source: str, current_prompt_id: str | None) -> UsageEvent | None:
    """Turn one assistant JSONL record into a UsageEvent, or None if it should
    be skipped (no usage, synthetic model, or an unparseable timestamp)."""
    extracted = _extract_usage(rec)
    if extracted is None:
        return None
    usage, model = extracted

    ts = _parse_timestamp(rec.get("timestamp"))
    if ts is None:
        return None

    return _build_event(rec, usage, model, source, ts, current_prompt_id)


class ClaudeCodeAdapter(PullAdapter):
    name = "claude_code"

    def __init__(self, claude_dir: Path | None = None) -> None:
        self.claude_dir = claude_dir or _default_claude_dir()

    def poll(self, state: IngestStateStore, sink: LedgerSink) -> int:
        if not self.claude_dir.is_dir():
            return 0
        total = 0
        for session_file in sorted(self.claude_dir.rglob("*.jsonl")):
            total += self._poll_file(session_file, state, sink)
        return total

    def _read_start_offset(self, path: Path, state: IngestStateStore) -> int:
        cursor_raw = state.get(self.name, str(path))
        cursor = json.loads(cursor_raw) if cursor_raw else {"offset": 0}
        start_offset = cursor.get("offset", 0)
        try:
            size = path.stat().st_size
        except OSError:
            return -1  # sentinel: file vanished/unreadable, caller returns 0
        return 0 if size < start_offset else start_offset

    def _process_line(
        self, line: str, current_prompt_id: str | None, sink: LedgerSink
    ) -> tuple[str | None, bool]:
        """Returns (updated current_prompt_id, whether an event was emitted)."""
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return current_prompt_id, False  # tolerate corrupt lines, never halt

        if rec.get("type") == "user" and rec.get("promptId"):
            current_prompt_id = rec.get("promptId")

        if rec.get("type") != "assistant":
            return current_prompt_id, False

        event = _record_to_event(rec, self.name, current_prompt_id)
        if event is None:
            return current_prompt_id, False

        try:
            sink.emit(event)
            return current_prompt_id, True
        except Exception as exc:  # nosec B110 - one bad record must not halt ingest
            log_error("adapters.claude_code", f"emit failed: {exc!r}")
            return current_prompt_id, False

    def _poll_file(self, path: Path, state: IngestStateStore, sink: LedgerSink) -> int:
        start_offset = self._read_start_offset(path, state)
        if start_offset < 0:
            return 0

        current_prompt_id: str | None = None
        count = 0
        try:
            with open(path, "rb") as f:
                f.seek(start_offset)
                for raw_line in f:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    current_prompt_id, emitted = self._process_line(line, current_prompt_id, sink)
                    if emitted:
                        count += 1
                new_offset = f.tell()
        except OSError as exc:
            log_error("adapters.claude_code", f"read failed for {path.name}: {exc!r}")
            return count

        state.set(self.name, str(path), json.dumps({"offset": new_offset}))
        return count
