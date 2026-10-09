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
import hmac
import json
import os
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from forecost.adapters.base import (
    IngestStateStore,
    LedgerSink,
    PullAdapter,
    UsageEvent,
    content_free_identifier,
    validate_usage_event,
)
from forecost.adapters.causal import runtime_meter_observation
from forecost.core.errlog import log_error
from forecost.core.local_identity import installation_key, keyed_fingerprint
from forecost.ledger.contracts import CausalIdentity, Observation
from forecost.ledger.evidence import append_observation, observation


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

_LIFECYCLE_OPERATIONS = {
    "Assistant": ("model", "completed"),
    "ExitPlanMode": ("human_approval", "completed"),
    "Agent": ("agent", "running"),
    "SubagentStart": ("agent", "running"),
    "SubagentStop": ("agent", "completed"),
    "PostToolUse": ("tool", "completed"),
    "PostToolBatch": ("tool", "completed"),
    "PostToolUseFailure": ("tool", "failed"),
    "Stop": ("agent", "completed"),
    "StopFailure": ("agent", "failed"),
    "SessionEnd": ("agent", "incomplete"),
    "Interrupt": ("human_approval", "cancelled"),
    "TaskCreated": ("agent", "queued"),
    "TaskCompleted": ("agent", "completed"),
    "BackgroundAgentSettled": ("agent", "completed"),
}


def _structural_id(record: Mapping[str, object], *names: str) -> str | None:
    for name in names:
        value = record.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def claude_lifecycle_observation(
    record: Mapping[str, object],
    event_name: str,
    *,
    source_sequence: int = 0,
    occurred_at: datetime | None = None,
) -> Observation:
    """Select causal/lifecycle facts from one transcript or hook record.

    Prompt, messages, tool input/output and arbitrary metadata are deliberately
    not inspected. Open-ended structural identifiers are irreversibly made
    opaque by :class:`Observation` normalization.
    """
    if event_name not in _LIFECYCLE_OPERATIONS:
        raise ValueError("unsupported Claude lifecycle event")
    operation_kind, lifecycle = _LIFECYCLE_OPERATIONS[event_name]
    session_id = _structural_id(record, "sessionId", "session_id")
    if session_id is None:
        raise ValueError("Claude lifecycle event needs session identity")
    run_id = _structural_id(record, "promptId", "prompt_id", "run_id") or session_id
    span_id = (
        _structural_id(
            record,
            "requestId",
            "uuid",
            "tool_use_id",
            "agent_id",
            "task_id",
            "hook_id",
        )
        or f"{event_name}:{source_sequence}"
    )
    parent_span_id = _structural_id(
        record, "parentUuid", "parent_uuid", "parent_tool_use_id", "parent_agent_id"
    )
    timestamp = occurred_at
    if timestamp is None:
        raw_timestamp = record.get("timestamp")
        timestamp = _parse_timestamp(raw_timestamp if isinstance(raw_timestamp, str) else None)
    timestamp = timestamp or datetime.now(timezone.utc)
    event_key = _structural_id(
        record,
        "event_id",
        "requestId",
        "uuid",
        "hook_id",
        "tool_use_id",
        "agent_id",
        "task_id",
    )
    return observation(
        producer="claude_code",
        event_kind="span",
        causal=CausalIdentity(
            conversation_id=session_id,
            trace_id=session_id,
            run_id=run_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            source_sequence=source_sequence,
            idempotency_key=event_key or f"{session_id}:{event_name}:{source_sequence}",
        ),
        payload={
            "operation_kind": operation_kind,
            "lifecycle": lifecycle,
            "agent_id": _structural_id(record, "agentId", "agent_id"),
            "workflow_node_id": _structural_id(record, "tool_name", "task_id"),
            "branch_id": _structural_id(record, "branch_id", "agentId", "agent_id"),
            "attempt_of_span_id": _structural_id(record, "attempt_of_span_id"),
            "checkpoint_id": _structural_id(record, "checkpoint_id"),
        },
        occurred_at=timestamp,
        observed_at=timestamp,
    )


def _causal_sequence(timestamp: datetime) -> int:
    """Stable chronological sequence shared by repeated transcript blocks."""
    return int(timestamp.timestamp() * 1_000)


def claude_record_observations(
    record: Mapping[str, object], current_prompt_id: str | None
) -> list[Observation]:
    """Map an assistant transcript record to one span and final token facts."""
    if record.get("type") != "assistant":
        return []
    mutable = dict(record)
    if current_prompt_id is not None:
        mutable["promptId"] = current_prompt_id
    timestamp_raw = record.get("timestamp")
    timestamp = _parse_timestamp(timestamp_raw if isinstance(timestamp_raw, str) else None)
    if timestamp is None:
        return []
    request_id = _structural_id(record, "requestId", "uuid")
    if request_id is None:
        return []
    sequence = _causal_sequence(timestamp)
    span = claude_lifecycle_observation(
        mutable,
        "Assistant",
        source_sequence=sequence,
        occurred_at=timestamp,
    )
    extracted = _extract_usage(mutable)
    if extracted is None:
        return [span]
    usage, _model = extracted
    meters: list[Observation] = []
    for offset, (field, meter_name) in enumerate(
        (
            ("input_tokens", "tokens.input"),
            ("output_tokens", "tokens.output"),
            ("cache_read_input_tokens", "tokens.cache_read"),
            ("cache_creation_input_tokens", "tokens.cache_write"),
        ),
        start=1,
    ):
        quantity = _usage_count(usage, field)
        if not quantity:
            continue
        meters.append(
            runtime_meter_observation(
                span.causal,
                producer="claude_code",
                idempotency_key=f"{request_id}:{field}",
                source_sequence=sequence + offset,
                meter_name=meter_name,
                quantity_micros=quantity * 1_000_000,
                occurred_at=timestamp,
                finality="final",
            )
        )
    return [span, *meters]


def _append_causal_record(record: dict, prompt_id: str | None, conn) -> int:
    try:
        return sum(
            int(append_observation(conn, item))
            for item in claude_record_observations(record, prompt_id)
        )
    except (TypeError, ValueError):
        log_error(
            "adapters.claude_code.causal",
            "CLAUDE_CAUSAL_RECORD_INVALID",
        )
        return 0


def _read_causal_path(
    path: Path,
    cursor: dict,
    conn,
    identity_key: bytes,
) -> tuple[int, str | None]:
    inserted = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        offset, prompt_id, prefix_digest = _resume_cursor(stream, cursor, identity_key)
        safe_offset = offset
        stream.seek(offset)
        for raw_line in stream:
            if not raw_line.endswith(b"\n"):
                break
            record = _parse_record(raw_line.decode("utf-8", errors="replace").strip())
            if record is not None:
                prompt_id = _updated_prompt_id(record, prompt_id)
                inserted += _append_causal_record(record, prompt_id, conn)
            safe_offset += len(raw_line)
            prefix_digest.update(raw_line)
        checkpoint = _verified_processed_checkpoint(
            stream, safe_offset, identity_key, prefix_digest
        )
        if checkpoint is None:
            # Bytes changed after they were processed. Keep the old cursor so
            # the next poll safely rewinds; observations above are idempotent.
            return inserted, None
        file_identity, boundary_identity = checkpoint
    return inserted, _encode_cursor(
        safe_offset,
        prompt_id,
        file_identity=file_identity,
        boundary_identity=boundary_identity,
    )


def _ingest_causal_path(
    path: Path,
    state: IngestStateStore,
    conn,
    source: str,
    identity_key: bytes,
) -> int:
    cursor_key = _cursor_key(source, str(path), identity_key)
    cursor_raw = state.get(source, cursor_key)
    cursor = _decode_cursor(cursor_raw)
    inserted, next_cursor = _read_causal_path(path, cursor, conn, identity_key)
    if next_cursor is not None and next_cursor != cursor_raw:
        state.set(source, cursor_key, next_cursor)
    return inserted


def ingest_causal_paths(paths: Iterable[Path], state: IngestStateStore, conn) -> int:
    """Incrementally append causal transcript facts using an independent cursor."""
    inserted = 0
    source = "claude_code_causal"
    eligible = [path for path in sorted(set(paths)) if path.is_file() and not path.is_symlink()]
    identity_key = installation_key()
    _migrate_legacy_cursors(state, source, identity_key)
    if not eligible:
        return 0
    for path in eligible:
        try:
            inserted += _ingest_causal_path(path, state, conn, source, identity_key)
        except OSError as error:
            log_error(
                "adapters.claude_code.causal",
                "CLAUDE_TRANSCRIPT_READ_FAILED",
                fingerprint_source=(str(path), error),
            )
    return inserted


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


_CURSOR_KEY_PREFIX = "cursor-hmac:v1:"
_CURSOR_KEY = re.compile(r"^cursor-hmac:v1:[0-9a-f]{64}$")
_FILE_IDENTITY = re.compile(r"^file-hmac:v1:[0-9a-f]{64}$")
_BOUNDARY_IDENTITY = re.compile(r"^boundary-hmac:v3:[0-9a-f]{64}$")
_CURSOR_HASH_CHUNK_BYTES = 64 * 1024


def _cursor_key(source: str, path_text: str, identity_key: bytes) -> str:
    """Bind one exact transcript identity to this installation and source.

    The full path participates in the HMAC, so equal basenames in two Claude
    workspace directories cannot share a cursor.  The path itself never leaves
    process memory.
    """
    digest = keyed_fingerprint(
        "claude-transcript-cursor-v1",
        source,
        path_text,
        key=identity_key,
    )
    return f"{_CURSOR_KEY_PREFIX}{digest}"


def _opaque_prompt_id(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return content_free_identifier("run", value)


def _new_prefix_digest(identity_key: bytes) -> hmac.HMAC:
    return hmac.new(
        identity_key,
        b"claude-transcript-prefix-v3\0",
        digestmod=hashlib.sha256,
    )


def _checkpoint_state(stream, offset: int, identity_key: bytes) -> tuple[str, str, hmac.HMAC]:
    """Read one descriptor's complete prefix and return keyed checkpoint state.

    The HMAC streams in bounded memory. Hashing the whole consumed prefix is
    intentional: sampling only the beginning and boundary can miss an in-place,
    same-length rewrite in the middle of a long transcript.
    """
    metadata = os.fstat(stream.fileno())
    original = stream.tell()
    digest = _new_prefix_digest(identity_key)
    stream.seek(0)
    remaining = offset
    try:
        while remaining:
            chunk = stream.read(min(remaining, _CURSOR_HASH_CHUNK_BYTES))
            if not chunk:
                raise OSError("transcript became shorter while checkpointing")
            digest.update(chunk)
            remaining -= len(chunk)
    finally:
        stream.seek(original)
    file_identity = "file-hmac:v1:" + keyed_fingerprint(
        "claude-transcript-file-v1", str(metadata.st_dev), str(metadata.st_ino), key=identity_key
    )
    return file_identity, "boundary-hmac:v3:" + digest.hexdigest(), digest


def _encode_cursor(
    offset: int,
    prompt_id: str | None,
    *,
    file_identity: str | None = None,
    boundary_identity: str | None = None,
) -> str:
    value: dict[str, object] = {
        "offset": max(offset, 0),
        "prompt_id": _opaque_prompt_id(prompt_id),
    }
    if file_identity is not None:
        value["file_identity"] = file_identity
    if boundary_identity is not None:
        value["boundary_identity"] = boundary_identity
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalized_cursor_value(value: str) -> tuple[int, str | None, str]:
    decoded = _decode_cursor(value)
    offset = _cursor_offset(decoded)
    prompt_id = _opaque_prompt_id(decoded.get("prompt_id"))
    raw_identity = decoded.get("file_identity")
    file_identity = (
        raw_identity
        if isinstance(raw_identity, str) and _FILE_IDENTITY.fullmatch(raw_identity)
        else None
    )
    raw_boundary = decoded.get("boundary_identity")
    boundary_identity = (
        raw_boundary
        if isinstance(raw_boundary, str) and _BOUNDARY_IDENTITY.fullmatch(raw_boundary)
        else None
    )
    return (
        offset,
        prompt_id,
        _encode_cursor(
            offset,
            prompt_id,
            file_identity=file_identity,
            boundary_identity=boundary_identity,
        ),
    )


def _merge_cursor_values(current: str | None, legacy: str) -> str:
    """Choose the least-advanced valid cursor so migration cannot skip usage."""
    legacy_offset, legacy_prompt, normalized_legacy = _normalized_cursor_value(legacy)
    if current is None:
        return normalized_legacy
    current_offset, current_prompt, normalized_current = _normalized_cursor_value(current)
    if current_offset < legacy_offset:
        return normalized_current
    if legacy_offset < current_offset:
        return normalized_legacy
    # At an equal byte boundary, conflicting prompt identities are discarded;
    # the next user record reconstructs the association without exposing text.
    prompt_id = current_prompt if current_prompt == legacy_prompt else None
    return _encode_cursor(current_offset, prompt_id)


def _migrate_legacy_cursors(
    state: IngestStateStore,
    source: str,
    identity_key: bytes,
) -> None:
    migration = getattr(state, "migrate_legacy_keys", None)
    if not callable(migration):
        return

    def target(old_key: str) -> str:
        if _CURSOR_KEY.fullmatch(old_key) is not None:
            return old_key
        return _cursor_key(source, old_key, identity_key)

    migration(source, target, _merge_cursor_values)


def _cursor_offset(cursor: dict) -> int:
    raw_offset = cursor.get("offset", 0)
    if not isinstance(raw_offset, bool) and isinstance(raw_offset, int) and raw_offset >= 0:
        return raw_offset
    return 0


def _cursor_prompt_id(cursor: dict) -> str | None:
    return _opaque_prompt_id(cursor.get("prompt_id"))


def _stored_checkpoint(cursor: dict) -> tuple[str, str] | None:
    stored_file = cursor.get("file_identity")
    stored_boundary = cursor.get("boundary_identity")
    if not (
        isinstance(stored_file, str)
        and _FILE_IDENTITY.fullmatch(stored_file)
        and isinstance(stored_boundary, str)
        and _BOUNDARY_IDENTITY.fullmatch(stored_boundary)
    ):
        return None
    return stored_file, stored_boundary


def _resume_cursor(stream, cursor: dict, identity_key: bytes) -> tuple[int, str | None, hmac.HMAC]:
    """Validate and bind a cursor to the descriptor that will be consumed."""
    offset = _cursor_offset(cursor)
    stored = _stored_checkpoint(cursor)
    if stored is None:
        return 0, None, _new_prefix_digest(identity_key)
    try:
        if os.fstat(stream.fileno()).st_size < offset:
            return 0, None, _new_prefix_digest(identity_key)
        current_file, current_boundary, digest = _checkpoint_state(stream, offset, identity_key)
    except OSError:
        return 0, None, _new_prefix_digest(identity_key)
    if hmac.compare_digest(stored[0], current_file) and hmac.compare_digest(
        stored[1], current_boundary
    ):
        return offset, _cursor_prompt_id(cursor), digest
    return 0, None, _new_prefix_digest(identity_key)


def _verified_processed_checkpoint(
    stream,
    offset: int,
    identity_key: bytes,
    processed_digest: hmac.HMAC,
) -> tuple[str, str] | None:
    """Publish only when rereading yields the exact bytes already processed."""
    try:
        file_identity, current_boundary, _digest = _checkpoint_state(stream, offset, identity_key)
    except OSError:
        return None
    processed_boundary = "boundary-hmac:v3:" + processed_digest.hexdigest()
    if not hmac.compare_digest(processed_boundary, current_boundary):
        return None
    return file_identity, processed_boundary


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
        log_error("adapters.claude_code", "CLAUDE_RECORD_INVALID")
        return False, True
    except Exception as exc:  # nosec B110 - transient failure must not advance the cursor
        log_error(
            "adapters.claude_code",
            "SINK_EMIT_FAILED",
            fingerprint_source=exc,
        )
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
            _migrate_legacy_cursors(state, self.name, installation_key())
            return 0
        return self.poll_paths(self.claude_dir.rglob("*.jsonl"), state, sink)

    def poll_paths(self, paths: Iterable[Path], state: IngestStateStore, sink: LedgerSink) -> int:
        """Poll an explicit bounded set of transcript files.

        Hook events know the triggering session path and use this method to
        avoid rescanning a user's lifetime transcript tree on every Stop.
        """
        eligible = [path for path in sorted(set(paths)) if path.is_file() and not path.is_symlink()]
        identity_key = installation_key()
        _migrate_legacy_cursors(state, self.name, identity_key)
        if not eligible:
            return 0
        return sum(self._poll_file(path, state, sink, identity_key) for path in eligible)

    def _read_cursor(
        self,
        path: Path,
        state: IngestStateStore,
        identity_key: bytes,
    ) -> tuple[str, str | None, dict]:
        cursor_key = _cursor_key(self.name, str(path), identity_key)
        cursor_raw = state.get(self.name, cursor_key)
        return cursor_key, cursor_raw, _decode_cursor(cursor_raw)

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
            log_error("adapters.claude_code", "CLAUDE_RECORD_INVALID")
            return current_prompt_id, False, True
        if event is None:
            return current_prompt_id, False, True

        inserted, accepted = _emit_event(event, sink)
        return current_prompt_id, inserted, accepted

    def _consume_file(
        self,
        path: Path,
        cursor: dict,
        sink: LedgerSink,
        identity_key: bytes,
    ) -> tuple[int, str | None]:
        count = 0
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as file_obj:
                start_offset, current_prompt_id, prefix_digest = _resume_cursor(
                    file_obj, cursor, identity_key
                )
                safe_offset = start_offset
                file_obj.seek(start_offset)
                for raw_line in file_obj:
                    current_prompt_id, inserted, accepted = _consume_raw_line(
                        raw_line, current_prompt_id, sink
                    )
                    if not accepted:
                        break
                    count += int(inserted)
                    safe_offset += len(raw_line)
                    prefix_digest.update(raw_line)
                checkpoint = _verified_processed_checkpoint(
                    file_obj, safe_offset, identity_key, prefix_digest
                )
                if checkpoint is None:
                    # Do not publish a cursor over bytes that changed after
                    # processing. The next poll rewinds and deduplicates.
                    return count, None
                file_identity, boundary_identity = checkpoint
        except OSError as exc:
            log_error(
                "adapters.claude_code",
                "CLAUDE_TRANSCRIPT_READ_FAILED",
                fingerprint_source=(str(path), exc),
            )
            return count, None
        return count, _encode_cursor(
            safe_offset,
            current_prompt_id,
            file_identity=file_identity,
            boundary_identity=boundary_identity,
        )

    def _poll_file(
        self,
        path: Path,
        state: IngestStateStore,
        sink: LedgerSink,
        identity_key: bytes,
    ) -> int:
        cursor_key, cursor_raw, cursor = self._read_cursor(path, state, identity_key)

        # Advance the cursor only past newline-terminated, successfully-accepted
        # lines. A partial final line (the writer is still appending it) or a
        # transient emit failure leaves the cursor before that record so the
        # next poll retries it — no silent undercount, no torn-line loss.
        count, next_cursor = self._consume_file(path, cursor, sink, identity_key)

        if next_cursor is not None and next_cursor != cursor_raw:
            state.set(self.name, cursor_key, next_cursor)
        return count
