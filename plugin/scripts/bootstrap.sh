#!/usr/bin/env sh
# Bootstraps forecost into the plugin's persistent data dir. If this script
# fails for any reason, every hook must degrade to a no-op (exit 0) — a broken
# forecost install must never brick Claude Code itself.
#
# Wired into the plugin lifecycle: hooks.json runs this as the first SessionStart
# hook (via ${CLAUDE_PLUGIN_ROOT}), creating/updating the venv in the persistent
# ${CLAUDE_PLUGIN_DATA} dir. Only an immutable PyPI release is installed; never
# execute a mutable branch from a hook lifecycle event.
set -e

DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/forecost}"
VENV_DIR="$DATA_DIR/venv"
PLUGIN_VERSION="0.3.0"
INSTALL_SPEC="forecost==$PLUGIN_VERSION"
LOCK_DIR="$DATA_DIR/install.lock"

mkdir -p "$DATA_DIR"

if [ -x "$VENV_DIR/bin/forecost-hook" ]; then
  installed_version=$("$VENV_DIR/bin/forecost" --version 2>/dev/null | tail -1 || echo "")
  case "$installed_version" in
    *"$PLUGIN_VERSION"*) exit 0 ;;
  esac
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  # Another session is installing. Every hook uses run-hook.sh and therefore
  # degrades to a no-op until that atomic install becomes visible.
  exit 0
fi

if ! TEMP_DIR=$(mktemp -d "$DATA_DIR/install.XXXXXX"); then
  rmdir "$LOCK_DIR" 2>/dev/null || true
  exit 0
fi
NEW_VENV="$TEMP_DIR/venv"

cleanup() {
  rm -rf -- "$TEMP_DIR"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if command -v uv >/dev/null 2>&1; then
  uv venv "$NEW_VENV" --quiet || exit 0
  uv pip install --python "$NEW_VENV/bin/python" "$INSTALL_SPEC" --quiet || exit 0
elif command -v python3 >/dev/null 2>&1; then
  python3 -m venv "$NEW_VENV" || exit 0
  "$NEW_VENV/bin/pip" install --quiet "$INSTALL_SPEC" || exit 0
else
  exit 0
fi

if [ -d "$VENV_DIR" ]; then
  mv "$VENV_DIR" "$TEMP_DIR/previous" || exit 0
fi
if ! mv "$NEW_VENV" "$VENV_DIR"; then
  if [ -d "$TEMP_DIR/previous" ]; then
    mv "$TEMP_DIR/previous" "$VENV_DIR" || true
  fi
  exit 0
fi

exit 0
