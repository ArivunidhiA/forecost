#!/usr/bin/env sh
# Bootstraps forecost into the plugin's persistent data dir. If this script
# fails for any reason, every hook must degrade to a no-op (exit 0) — a broken
# forecost install must never brick Claude Code itself.
#
# Wired into the plugin lifecycle: hooks.json runs this as the first SessionStart
# hook (via ${CLAUDE_PLUGIN_ROOT}), creating/updating the venv in the persistent
# ${CLAUDE_PLUGIN_DATA} dir that the other hooks invoke. Once forecost is on PyPI,
# switch INSTALL_SPEC to a "forecost==X.Y.Z" pin for reproducible installs.
set -e

DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/forecost}"
VENV_DIR="$DATA_DIR/venv"
PLUGIN_VERSION="0.3.0"
INSTALL_SPEC="forecost @ git+https://github.com/ArivunidhiA/forecost.git@main"

mkdir -p "$DATA_DIR"

if [ -x "$VENV_DIR/bin/forecost-hook" ]; then
  installed_version=$("$VENV_DIR/bin/forecost" --version 2>/dev/null | tail -1 || echo "")
  case "$installed_version" in
    *"$PLUGIN_VERSION"*) exit 0 ;;
  esac
fi

if command -v uv >/dev/null 2>&1; then
  uv venv "$VENV_DIR" --quiet || exit 0
  uv pip install --python "$VENV_DIR/bin/python" "$INSTALL_SPEC" --quiet || exit 0
elif command -v python3 >/dev/null 2>&1; then
  python3 -m venv "$VENV_DIR" || exit 0
  "$VENV_DIR/bin/pip" install --quiet "$INSTALL_SPEC" || exit 0
else
  exit 0
fi

exit 0
