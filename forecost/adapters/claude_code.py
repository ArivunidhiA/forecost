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

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from forecost.adapters.base import (
    IngestStateStore,
    LedgerSink,
    PullAdapter,
    UsageEvent,
    validate_usage_event,
)
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


_SAFE_ENUM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$")


def _assistant_message(rec: dict) -> Mapping[str, object]:
    message = rec.get("message") or {}
    if not isinstance(message, Mapping):
        raise ValueError("assistant message has an invalid shape")
    return message


def _assistant_usage(message: Mapping[str, object]) -> Mapping[str, object] | None:
    usage = message.get("usage")
    if usage is not None and not isinstance(usage, Mapping):
        raise ValueError("assistant usage has an invalid shape")
    return usage


def _assistant_model(message: Mapping[str, object]) -> str | None:
    model = message.get("model")
    if model is not None and not isinstance(model, str):
        raise ValueError("assistant model has an invalid shape")
    return model


def _billable_usage(
    usage: Mapping[str, object] | None, model: str | None
) -> tuple[Mapping[str, object], str] | None:
    if not usage or not model or model == "<synthetic>":
        return None
    return usage, model


def _validate_assistant_model(model: str) -> None:
    if len(model) > 256 or _SAFE_ENUM.fullmatch(model) is None:
        raise ValueError("assistant model is not a safe identifier")


def _extract_usage(rec: dict) -> tuple[Mapping[str, object], str] | None:
    """Return (usage_dict, model) if this record is a billable assistant
    message, else None (no usage, missing model, or a synthetic placeholder)."""
    message = _assistant_message(rec)
    usage = _assistant_usage(message)
    model = _assistant_model(message)
    billable = _billable_usage(usage, model)
    if billable is None:
        return None
    usage, model = billable
    _validate_assistant_model(model)
    return usage, model


def _usage_count(usage: Mapping[str, object], key: str) -> int:
    value = usage.get(key, 0)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("assistant usage token count is invalid")
    return value


def _anonymous_event_uid(
    rec: dict, usage: Mapping[str, object], model: str, current_prompt_id: str | None
) -> str:
    """Hash non-content identity and usage facts for records without stable ids."""
    identity = {
        "session_id": rec.get("sessionId"),
        "agent_id": rec.get("agentId"),
        "prompt_id": current_prompt_id or rec.get("promptId"),
        "timestamp": rec.get("timestamp"),
        "model": model,
        "input_tokens": _usage_count(usage, "input_tokens"),
        "output_tokens": _usage_count(usage, "output_tokens"),
        "cache_read_input_tokens": _usage_count(usage, "cache_read_input_tokens"),
        "cache_creation_input_tokens": _usage_count(usage, "cache_creation_input_tokens"),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"cc:anon:{hashlib.sha256(encoded).hexdigest()}"


def _event_uid(
    rec: dict, usage: Mapping[str, object], model: str, current_prompt_id: str | None
) -> str:
    request_id = rec.get("requestId")
    if request_id:
        return f"cc:{request_id}"
    record_uuid = rec.get("uuid")
    if record_uuid:
        return f"cc:uuid:{record_uuid}"
    return _anonymous_event_uid(rec, usage, model, current_prompt_id)


def _safe_entrypoint(rec: dict) -> str | None:
    entrypoint = rec.get("entrypoint")
    if (
        isinstance(entrypoint, str)
        and len(entrypoint) <= 256
        and _SAFE_ENUM.fullmatch(entrypoint) is not None
    ):
        return entrypoint
    return None


def _build_event(
    rec: dict,
    usage: Mapping[str, object],
    model: str,
    source: str,
    ts,
    current_prompt_id: str | None,
) -> UsageEvent:
    # Claude Code writes one JSONL record per *content block* of a single API
    # response, and every one of those records repeats the identical
    # message.usage. Keying on the per-record uuid (the old bug) billed each
    # block as a separate event — up to ~2.25x inflation on real transcripts.
    # Key on the requestId so one API response counts exactly once; INSERT OR
    # IGNORE on event_uid then collapses the repeated blocks. Fall back to the
    # uuid only when a record carries no requestId (rare, non-standard records).
    event_uid = _event_uid(rec, usage, model, current_prompt_id)
    event = UsageEvent(
        event_uid=event_uid,
        ts=ts,
        source=source,
        model=model,
        provider="anthropic",
        session_uid=rec.get("sessionId"),
        run_id=current_prompt_id,
        agent="claude-code",
        workspace_path=rec.get("cwd"),
        tokens_in=_usage_count(usage, "input_tokens"),
        tokens_out=_usage_count(usage, "output_tokens"),
        tokens_cache_read=_usage_count(usage, "cache_read_input_tokens"),
        tokens_cache_write=_usage_count(usage, "cache_creation_input_tokens"),
        metadata={
            "is_sidechain": bool(rec.get("isSidechain")),
            "entrypoint": _safe_entrypoint(rec),
        },
    )
    validate_usage_event(event)
    return event


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


def _decode_cursor(cursor_raw: str | None) -> dict:
    try:
        cursor = json.loads(cursor_raw) if cursor_raw else {}
    except (json.JSONDecodeError, TypeError):
        return {}
    return cursor if isinstance(cursor, dict) else {}


def _cursor_offset(cursor: dict) -> int:
    raw_offset = cursor.get("offset", 0)
    if isinstance(raw_offset, int) and raw_offset >= 0:
        return raw_offset
    return 0


def _cursor_prompt_id(cursor: dict) -> str | None:
    raw_prompt_id = cursor.get("prompt_id")
    return raw_prompt_id if isinstance(raw_prompt_id, str) else None


def _parse_record(line: str) -> dict | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def _updated_prompt_id(rec: dict, current_prompt_id: str | None) -> str | None:
    prompt_id = rec.get("promptId")
    if rec.get("type") == "user" and isinstance(prompt_id, str):
        return prompt_id
    return current_prompt_id


def _emit_event(event: UsageEvent, sink: LedgerSink) -> tuple[bool, bool]:
    try:
        return sink.emit(event) is not False, True
    except ValueError:
        # Complete but permanently invalid source data must not pin the cursor.
        log_error("adapters.claude_code", "skipped a schema-invalid usage record")
        return False, True
    except Exception as exc:  # nosec B110 - transient failure must not advance the cursor
        log_error("adapters.claude_code", f"emit failed, will retry next poll: {exc!r}")
        return False, False


def _consume_raw_line(
    raw_line: bytes, current_prompt_id: str | None, sink: LedgerSink
) -> tuple[str | None, bool, bool]:
    """Return updated prompt id, whether an event inserted, and whether to advance."""
    if not raw_line.endswith(b"\n"):
        return current_prompt_id, False, False
    line = raw_line.decode("utf-8", errors="replace").strip()
    if not line:
        return current_prompt_id, False, True
    return ClaudeCodeAdapter._process_line(line, current_prompt_id, sink)


class ClaudeCodeAdapter(PullAdapter):
    name = "claude_code"

    def __init__(self, claude_dir: Path | None = None) -> None:
        self.claude_dir = claude_dir or _default_claude_dir()

    def poll(self, state: IngestStateStore, sink: LedgerSink) -> int:
        if not self.claude_dir.is_dir():
            return 0
        return self.poll_paths(self.claude_dir.rglob("*.jsonl"), state, sink)

    def poll_paths(self, paths: Iterable[Path], state: IngestStateStore, sink: LedgerSink) -> int:
        """Poll an explicit bounded set of transcript files.

        Hook events know the triggering session path and use this method to
        avoid rescanning a user's lifetime transcript tree on every Stop.
        """
        return sum(
            self._poll_file(path, state, sink) for path in sorted(set(paths)) if path.is_file()
        )

    def _read_cursor(self, path: Path, state: IngestStateStore) -> tuple[int, str | None]:
        cursor_raw = state.get(self.name, str(path))
        cursor = _decode_cursor(cursor_raw)
        start_offset = _cursor_offset(cursor)
        prompt_id = _cursor_prompt_id(cursor)
        try:
            size = path.stat().st_size
        except OSError:
            return -1, None  # sentinel: file vanished/unreadable, caller returns 0
        if size < start_offset:
            return 0, None
        return start_offset, prompt_id

    @staticmethod
    def _process_line(
        line: str, current_prompt_id: str | None, sink: LedgerSink
    ) -> tuple[str | None, bool, bool]:
        """Process one line. Returns (current_prompt_id, inserted, accepted).

        - inserted: a NEW usage_event was recorded (False for duplicates and
          non-billable records) — used for the honest ingested count.
        - accepted: True unless a *transient* emit failure occurred. On
          accepted=False the caller must stop and NOT advance the cursor past
          this record, so the event is retried (idempotently) next poll. A
          corrupt or non-billable line is accepted (safe to skip).
        """
        rec = _parse_record(line)
        if rec is None:
            return current_prompt_id, False, True  # complete but corrupt line: safe to skip

        current_prompt_id = _updated_prompt_id(rec, current_prompt_id)

        if rec.get("type") != "assistant":
            return current_prompt_id, False, True

        try:
            event = _record_to_event(rec, ClaudeCodeAdapter.name, current_prompt_id)
        except (TypeError, ValueError):
            log_error("adapters.claude_code", "skipped a schema-invalid assistant record")
            return current_prompt_id, False, True
        if event is None:
            return current_prompt_id, False, True

        inserted, accepted = _emit_event(event, sink)
        return current_prompt_id, inserted, accepted

    def _consume_file(
        self,
        path: Path,
        start_offset: int,
        current_prompt_id: str | None,
        sink: LedgerSink,
    ) -> tuple[int, int, str | None]:
        count = 0
        safe_offset = start_offset
        try:
            with open(path, "rb") as file_obj:
                file_obj.seek(start_offset)
                for raw_line in file_obj:
                    current_prompt_id, inserted, accepted = _consume_raw_line(
                        raw_line, current_prompt_id, sink
                    )
                    if not accepted:
                        break
                    count += int(inserted)
                    safe_offset += len(raw_line)
        except OSError as exc:
            log_error("adapters.claude_code", f"read failed for {path.name}: {exc!r}")
        return count, safe_offset, current_prompt_id

    def _poll_file(self, path: Path, state: IngestStateStore, sink: LedgerSink) -> int:
        start_offset, current_prompt_id = self._read_cursor(path, state)
        if start_offset < 0:
            return 0

        # Advance the cursor only past newline-terminated, successfully-accepted
        # lines. A partial final line (the writer is still appending it) or a
        # transient emit failure leaves the cursor before that record so the
        # next poll retries it — no silent undercount, no torn-line loss.
        count, safe_offset, current_prompt_id = self._consume_file(
            path, start_offset, current_prompt_id, sink
        )

        if safe_offset != start_offset:  # skip a no-op write when nothing new was consumed
            state.set(
                self.name,
                str(path),
                json.dumps({"offset": safe_offset, "prompt_id": current_prompt_id}),
            )
        return count
