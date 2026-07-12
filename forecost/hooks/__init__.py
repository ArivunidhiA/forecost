"""Claude Code hook handlers. Fast, fail-open, content-free.

Contract (verified against Claude Code's documented hooks interface): each
handler reads a JSON payload from stdin and writes a JSON response to stdout.
ANY unhandled exception must result in exit 0 with empty/minimal stdout —
a broken forecost install must never brick the host agent (BASEMENT.md L4).
"""
