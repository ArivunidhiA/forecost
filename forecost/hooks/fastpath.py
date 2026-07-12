"""forecost-hook: the Claude Code hook entry point.

Usage: forecost-hook <session-start|prompt-submit|pre-tool|stop>

Contract: stdin is the hook's JSON payload; stdout (on exit 0) is parsed by
Claude Code as the hook's structured response. ANY unhandled exception here
results in exit 0 with empty stdout — a broken forecost install degrades to
"no forecost," never to "no Claude Code" (BASEMENT.md law L4).
"""

from __future__ import annotations

import contextlib
import json
import sys

_COMMANDS = {
    "session-start": "handle_session_start",
    "prompt-submit": "handle_preflight",
    "pre-tool": "handle_gate",
    "stop": "handle_reconcile",
}


def _read_payload() -> dict | None:
    """Returns the parsed stdin payload, or None on any parse failure."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return None


def _dispatch(command: str, payload: dict) -> None:
    """Runs the handler and prints its JSON result. Any exception here is the
    caller's responsibility to swallow — fail-open is enforced by main()."""
    from forecost.hooks import handlers

    handler = getattr(handlers, _COMMANDS[command])
    result = handler(payload)
    if result:
        print(json.dumps(result))  # noqa: T201 - this IS the hook's stdout contract


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        # Not a recognized hook invocation; exit 0 silently (never break the caller).
        sys.exit(0)
    command = sys.argv[1]

    payload = _read_payload()
    if payload is None:
        sys.exit(0)

    try:
        _dispatch(command, payload)
    except Exception as exc:  # nosec B110 - fail-open is the hook's product law
        with contextlib.suppress(Exception):
            from forecost.core.errlog import log_error

            log_error(f"hooks.{command}", f"handler failed: {exc!r}")
    sys.exit(0)


if __name__ == "__main__":
    main()
