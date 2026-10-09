#!/usr/bin/env sh
# Fail-open launcher shared by every Claude Code hook. It executes only the
# exact hook in the plugin-owned data environment. PATH fallback is forbidden.
# Ownership/mode checks narrow accidental and project-path substitution; they
# are not authentication against a process with the same OS-user privileges.

DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/forecost}"
HOOK_NAME="${1:-}"

case "$HOOK_NAME" in
  session-start|prompt-submit|pre-tool|stop|session-end|lifecycle) ;;
  *) exit 0 ;;
esac

HOOK_BIN="$DATA_DIR/venv/bin/forecost-hook"

case "$DATA_DIR" in
  /*) ;;
  *) exit 0 ;;
esac

path_owner() {
  stat -f '%u' "$1" 2>/dev/null || stat -c '%u' "$1" 2>/dev/null
}

path_mode() {
  stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1" 2>/dev/null
}

safe_owned_path() {
  candidate="$1"
  [ -e "$candidate" ] || return 1
  [ ! -L "$candidate" ] || return 1
  current_uid=$(id -u 2>/dev/null) || return 1
  candidate_uid=$(path_owner "$candidate") || return 1
  [ "$candidate_uid" = "$current_uid" ] || return 1
  candidate_mode=$(path_mode "$candidate") || return 1
  case "$candidate_mode" in
    ''|*[!0-7]*) return 1 ;;
  esac
  # Reject group/world-writable roots, environments, directories, or binaries.
  [ $((0$candidate_mode & 022)) -eq 0 ] || return 1
}

no_symlink_components() {
  candidate="$1"
  while [ "$candidate" != "/" ]; do
    [ ! -L "$candidate" ] || return 1
    candidate=${candidate%/*}
    [ -n "$candidate" ] || candidate="/"
  done
}

no_symlink_components "$DATA_DIR" || exit 0
safe_owned_path "$DATA_DIR" || exit 0
safe_owned_path "$DATA_DIR/venv" || exit 0
safe_owned_path "$DATA_DIR/venv/bin" || exit 0
safe_owned_path "$HOOK_BIN" || exit 0
[ -x "$HOOK_BIN" ] || exit 0

"$HOOK_BIN" "$HOOK_NAME" || exit 0
