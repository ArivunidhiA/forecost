#!/usr/bin/env sh
# Bootstraps a pinned forecost install into the plugin's persistent data dir.
# Runs on SessionStart via hooks.json before forecost-hook is invoked. If this
# script fails for any reason, every hook must degrade to a no-op (exit 0) —
# a broken forecost install must never brick Claude Code itself.
set -e

DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/forecost}"
VENV_DIR="$DATA_DIR/venv"
PINNED_VERSION="0.3.0"

mkdir -p "$DATA_DIR"

if [ -x "$VENV_DIR/bin/forecost-hook" ]; then
  installed_version=$("$VENV_DIR/bin/forecost" --version 2>/dev/null | tail -1 || echo "")
  case "$installed_version" in
    *"$PINNED_VERSION"*) exit 0 ;;
  esac
fi

if command -v uv >/dev/null 2>&1; then
  uv venv "$VENV_DIR" --quiet || exit 0
  uv pip install --python "$VENV_DIR/bin/python" "forecost==$PINNED_VERSION" --quiet || exit 0
elif command -v python3 >/dev/null 2>&1; then
  python3 -m venv "$VENV_DIR" || exit 0
  "$VENV_DIR/bin/pip" install --quiet "forecost==$PINNED_VERSION" || exit 0
else
  exit 0
fi

exit 0
