"""Optional MCP entry point with a useful base-install diagnostic.

The base wheel intentionally has no MCP dependency.  Console-script discovery
must therefore stay import-safe and explain how to opt in instead of exposing a
``ModuleNotFoundError`` from an entry point advertised by package metadata.
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
                "forecost-mcp requires the optional MCP dependency. "
                "Install it with: pip install 'forecost[mcp]'\n"
            )
            raise SystemExit(2) from None
        raise
    server_main()


if __name__ == "__main__":  # pragma: no cover - console-script wrapper
    main()
