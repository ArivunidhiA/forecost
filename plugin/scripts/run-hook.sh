#!/usr/bin/env sh
# Fail-open launcher shared by every Claude Code hook. A missing, interrupted,
# or incompatible install becomes a no-op instead of a command-not-found error.

DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/forecost}"
HOOK_NAME="${1:-}"

case "$HOOK_NAME" in
  session-start|prompt-submit|pre-tool|stop) ;;
  *) exit 0 ;;
esac

HOOK_BIN="$DATA_DIR/venv/bin/forecost-hook"
if [ ! -x "$HOOK_BIN" ]; then
  HOOK_BIN=$(command -v forecost-hook 2>/dev/null || true)
fi
[ -n "$HOOK_BIN" ] && [ -x "$HOOK_BIN" ] || exit 0

"$HOOK_BIN" "$HOOK_NAME" || exit 0
