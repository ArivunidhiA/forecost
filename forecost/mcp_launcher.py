"""Optional MCP module launcher with a useful base-install diagnostic.

The base wheel intentionally has no MCP dependency or MCP console script.
After installing ``forecost[mcp]``, launch the server explicitly with
``python -m forecost.mcp_launcher``.  Keeping this opt-in prevents a broken
entry point from being advertised by a minimal installation.
"""

from __future__ import annotations

import sys


def main() -> None:
    """Start the MCP server when its optional dependency is available."""
    try:
        from forecost.mcp.server import main as server_main
    except ModuleNotFoundError as error:
        if error.name == "mcp":
            sys.stderr.write(
                "Forecost's MCP server is optional. Install it with "
                "pip install 'forecost[mcp]', then run "
                "python -m forecost.mcp_launcher.\n"
            )
            raise SystemExit(2) from None
        raise
    server_main()


if __name__ == "__main__":  # pragma: no cover - console-script wrapper
    main()
