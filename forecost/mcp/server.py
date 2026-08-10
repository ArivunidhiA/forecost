"""Read-only MCP access to Forecost's canonical receipt ledger.

The supported MCP surface intentionally contains no forecast-era project reads,
pricing guesses, or mutations.  MCP clients can discover runs and fetch the
same stable receipt returned by the installed CLI; both tools read only
``ledger.db``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import cast

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from forecost.ledger.db import get_ledger_db
from forecost.ledger.receipts import build_receipt

MCP_SCHEMA_VERSION = 1
MCP_STORE_BOUNDARY = "canonical-ledger:ledger.db:read-only"
SUPPORTED_MCP_TOOLS = ("forecost_list_runs", "forecost_get_receipt")

mcp = FastMCP("forecost")

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _error(code: str, message: str, *, hint: str | None = None) -> str:
    payload: dict[str, object] = {
        "schema_version": MCP_SCHEMA_VERSION,
        "store": MCP_STORE_BOUNDARY,
        "error": {"code": code, "message": message},
    }
    if hint is not None:
        cast(dict[str, object], payload["error"])["hint"] = hint
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@mcp.tool(annotations=_READ_ONLY)
def forecost_list_runs(limit: int = 20) -> str:
    """List local canonical runs and their evidence summaries (read-only)."""
    if limit < 1 or limit > 200:
        return _error("invalid-limit", "limit must be between 1 and 200")
    try:
        conn = get_ledger_db()
        rows = conn.execute(
            "SELECT run_id, lifecycle, observed_at FROM causal_runs "
            "ORDER BY observed_at DESC, run_id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        runs: list[dict[str, object]] = []
        for row in rows:
            receipt = build_receipt(conn, row["run_id"])
            evidence = cast(dict[str, object], receipt["evidence"])
            outcome = cast(dict[str, object], receipt["outcome"])
            runs.append(
                {
                    "run_id": row["run_id"],
                    "lifecycle": row["lifecycle"],
                    "observed_at": row["observed_at"],
                    "evidence_state": evidence["state"],
                    "outcome": outcome["status"],
                    "economic_totals_micros": receipt["economic_totals_micros"],
                }
            )
        return json.dumps(
            {
                "schema_version": MCP_SCHEMA_VERSION,
                "store": MCP_STORE_BOUNDARY,
                "runs": runs,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    except sqlite3.Error as error:
        return _error("ledger-database", str(error))
    except ValueError as error:
        return _error("receipt-evidence", str(error))


@mcp.tool(annotations=_READ_ONLY)
def forecost_get_receipt(run_id: str) -> str:
    """Return one stable, content-free canonical receipt (read-only)."""
    if not run_id or len(run_id) > 512:
        return _error("invalid-run-id", "run_id must be a non-empty bounded identifier")
    try:
        receipt = build_receipt(get_ledger_db(), run_id)
        return json.dumps(
            {
                "schema_version": MCP_SCHEMA_VERSION,
                "store": MCP_STORE_BOUNDARY,
                "receipt": receipt,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    except sqlite3.Error as error:
        return _error("ledger-database", str(error))
    except ValueError as error:
        return _error(
            "unknown-run",
            str(error),
            hint="Use forecost_list_runs to find canonical run identifiers.",
        )


def main() -> None:
    """Serve the canonical read-only tools over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - module entry point
    main()
