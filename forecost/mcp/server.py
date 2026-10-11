"""Read-only MCP access to Forecost's canonical receipt ledger.

The supported MCP surface intentionally contains no forecast-era project reads,
pricing guesses, or mutations. MCP clients can discover runs and fetch the
same stable receipt returned by the installed CLI; all tools read only
``ledger.db``. A third diagnostic tool projects the same strict comparison
result as the CLI; without a predeclared cohort manifest it always abstains
rather than calling two unrelated totals "savings". Read-only means no
Forecost row, schema, migration, or integration mutation. SQLite itself may
create WAL/SHM coordination sidecars while reading the live WAL database.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from typing import cast

from mcp.types import ToolAnnotations

try:  # mcp >= 2 renamed FastMCP to MCPServer
    from mcp.server.mcpserver import (  # type: ignore[import-not-found,unused-ignore]  # pyright: ignore[reportMissingImports]
        MCPServer as _McpServer,
    )
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import (  # type: ignore[import-not-found,unused-ignore]  # pyright: ignore[reportMissingImports]
        FastMCP as _McpServer,
    )

from forecost.comparison import ComparisonConfigurationError, compare_runs_diagnostic
from forecost.core.paths import UnsafeDataPathError
from forecost.ledger.db import get_readonly_ledger_db
from forecost.ledger.receipts import build_receipt

MCP_SCHEMA_VERSION = 1
MCP_STORE_BOUNDARY = "canonical-ledger:ledger.db:read-only"
SUPPORTED_MCP_TOOLS = (
    "forecost_list_runs",
    "forecost_get_receipt",
    "forecost_compare_runs",
)
_COMPARISON_AUTHORITIES = frozenset(
    {"list_rate", "gateway_estimate", "provider_estimate", "user_imported_claim"}
)
_COMPARISON_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,255}$")

mcp = _McpServer("forecost")

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
        with closing(get_readonly_ledger_db()) as conn:
            rows = conn.execute(
                "SELECT run_id, lifecycle, observed_at FROM causal_runs "
                "ORDER BY observed_at DESC, run_id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            runs: list[dict[str, object]] = []
            for row in rows:
                receipt = build_receipt(conn, row["run_id"])
                evidence = cast(dict[str, object], receipt["evidence"])
                profiles = evidence.get("claim_profiles")
                profile_summaries = profiles if isinstance(profiles, dict) else {}
                outcome = cast(dict[str, object], receipt["outcome"])
                runs.append(
                    {
                        "run_id": row["run_id"],
                        "lifecycle": row["lifecycle"],
                        "observed_at": row["observed_at"],
                        "evidence_profiles": profile_summaries,
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
    except (sqlite3.Error, OSError, UnsafeDataPathError) as error:
        return _error("ledger-database", str(error))
    except ValueError as error:
        return _error("receipt-evidence", str(error))


@mcp.tool(annotations=_READ_ONLY)
def forecost_get_receipt(run_id: str) -> str:
    """Return one stable, content-minimizing canonical receipt (read-only)."""
    if not run_id or len(run_id) > 512:
        return _error("invalid-run-id", "run_id must be a non-empty bounded identifier")
    try:
        with closing(get_readonly_ledger_db()) as conn:
            exists = conn.execute(
                "SELECT 1 FROM causal_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if exists is None:
                return _error(
                    "unknown-run",
                    "canonical run was not found",
                    hint="Use forecost_list_runs to find canonical run identifiers.",
                )
            receipt = build_receipt(conn, run_id)
        return json.dumps(
            {
                "schema_version": MCP_SCHEMA_VERSION,
                "store": MCP_STORE_BOUNDARY,
                "receipt": receipt,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    except (sqlite3.Error, OSError, UnsafeDataPathError) as error:
        return _error("ledger-database", str(error))
    except ValueError as error:
        return _error("receipt-evidence", str(error))


@mcp.tool(annotations=_READ_ONLY)
def forecost_compare_runs(
    baseline_run_id: str,
    candidate_run_id: str,
    authority: str = "list_rate",
    currency: str = "USD",
) -> str:
    """Diagnose two local runs without claiming they are a matched experiment.

    The result may expose an authority-specific observed delta, but its decision
    is always ``abstain`` until a caller supplies the versioned, digest-bound
    cohort manifest required by the CLI's full comparison mode. This tool is
    read-only and does not infer workload or outcome identity from run shape.
    """
    if _COMPARISON_RUN_ID.fullmatch(baseline_run_id) is None:
        return _error(
            "invalid-baseline-run-id",
            "baseline_run_id must be a bounded opaque identifier",
        )
    if _COMPARISON_RUN_ID.fullmatch(candidate_run_id) is None:
        return _error(
            "invalid-candidate-run-id",
            "candidate_run_id must be a bounded opaque identifier",
        )
    if authority not in _COMPARISON_AUTHORITIES:
        return _error(
            "unsupported-authority",
            "diagnostic authority is not supported",
            hint="Use list_rate, gateway_estimate, provider_estimate, or user_imported_claim.",
        )
    if currency != "USD":
        return _error(
            "unsupported-currency",
            "comparison v1 performs no currency conversion",
            hint="Use USD.",
        )
    try:
        with closing(get_readonly_ledger_db()) as conn:
            result = compare_runs_diagnostic(
                conn,
                baseline_run_id,
                candidate_run_id,
                authority=authority,
                currency=currency,
                line_items=("model_inference",),
            )
        return json.dumps(
            {
                "schema_version": MCP_SCHEMA_VERSION,
                "store": MCP_STORE_BOUNDARY,
                "comparison": result,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    except (sqlite3.Error, OSError, UnsafeDataPathError) as error:
        return _error("ledger-database", str(error))
    except ComparisonConfigurationError as error:
        return _error("invalid-comparison", str(error))


def main() -> None:
    """Serve the canonical read-only tools over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - module entry point
    main()
