"""ForeCost MCP Server — query LLM cost data from any AI assistant."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from forecost.db import (
    get_daily_costs,
    get_or_create_db,
    get_recent_usage_logs,
)
from forecost.forecaster import ProjectForecaster
from forecost.pricing import calculate_cost, get_provider

mcp = FastMCP("forecost_mcp")


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


class CostSummaryInput(BaseModel):
    """Input parameters for the cost summary tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_id: int = Field(
        description="ForeCost project ID. Use forecost_list_projects to find it."
    )
    group_by: Literal["day", "model", "provider"] | None = Field(
        default="day",
        description="How to aggregate costs: by day, model, or provider",
    )
    days: int | None = Field(
        default=None,
        ge=1,
        description="Limit to the last N days. Omit for all time.",
    )


class ForecastInput(BaseModel):
    """Input parameters for the forecast tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_id: int = Field(
        description="ForeCost project ID. Use forecost_list_projects to find it."
    )


class AnomalyInput(BaseModel):
    """Input parameters for the anomaly detection tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_id: int = Field(
        description="ForeCost project ID. Use forecost_list_projects to find it."
    )


class RecentCallsInput(BaseModel):
    """Input parameters for the recent calls tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_id: int = Field(
        description="ForeCost project ID. Use forecost_list_projects to find it."
    )
    limit: int | None = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of recent calls to return",
    )


class TrackCallInput(BaseModel):
    """Input parameters for the track call tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    project_id: int = Field(
        description="ForeCost project ID. Use forecost_list_projects to find it."
    )
    model: str = Field(
        min_length=1,
        description="Model name, e.g. 'gpt-4o', 'claude-sonnet-4-20250514'",
    )
    tokens_in: int = Field(ge=0, description="Input/prompt token count")
    tokens_out: int = Field(ge=0, description="Output/completion token count")
    cost_usd: float | None = Field(
        default=None,
        ge=0,
        description="Cost in USD. If omitted, auto-calculated from ForeCost's pricing database.",
    )


# ---------------------------------------------------------------------------
# Tool 1: forecost_list_projects
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def forecost_list_projects() -> str:
    """List all ForeCost projects with their IDs, names, paths, and baselines."""
    try:
        conn = get_or_create_db()
        rows = conn.execute(
            "SELECT id, name, path, baseline_daily_cost, baseline_total_days, "
            "baseline_total_cost, created_at FROM projects ORDER BY created_at DESC"
        ).fetchall()
        projects = [dict(r) for r in rows]
        return json.dumps(projects, indent=2, default=str)
    except sqlite3.Error as e:
        return f"Error: Database error — {e}. Ensure ForeCost is initialized (run 'forecost init')."
    except Exception as e:
        return f"Error: Unexpected error ({type(e).__name__}): {e}"


# ---------------------------------------------------------------------------
# Tool 2: forecost_get_cost_summary
# ---------------------------------------------------------------------------


def _summarize_by_day(params: CostSummaryInput, conn: object) -> dict:
    """Build cost summary grouped by day."""
    raw = get_daily_costs(params.project_id)
    rows = [{"date": day, "cost_usd": cost, "total_tokens": tokens} for day, cost, tokens in raw]

    if params.days is not None:
        cutoff_str = (datetime.now(timezone.utc).date() - timedelta(days=params.days)).isoformat()
        rows = [r for r in rows if r["date"] >= cutoff_str]
        count_row = conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) as cnt FROM usage_logs WHERE project_id = ? AND date(timestamp) >= ?",
            (params.project_id, cutoff_str),
        ).fetchone()
    else:
        count_row = conn.execute(  # type: ignore[union-attr]
            "SELECT COUNT(*) as cnt FROM usage_logs WHERE project_id = ?",
            (params.project_id,),
        ).fetchone()

    return {
        "group_by": "day",
        "data": rows,
        "totals": {
            "total_cost_usd": sum(r["cost_usd"] for r in rows),
            "total_tokens": sum(r["total_tokens"] for r in rows),
            "total_calls": count_row["cnt"] if count_row else 0,
        },
    }


_ALLOWED_GROUP_COLUMNS = frozenset({"model", "provider"})


def _summarize_by_column(params: CostSummaryInput, conn: object, column: str) -> dict:
    """Build cost summary grouped by model or provider."""
    if column not in _ALLOWED_GROUP_COLUMNS:
        msg = f"Invalid group column: {column}"
        raise ValueError(msg)
    query = (
        f"SELECT {column}, SUM(cost_usd) as total_cost, "  # nosec B608  # noqa: S608
        "SUM(tokens_in + tokens_out) as total_tokens, COUNT(*) as call_count "
        f"FROM usage_logs WHERE project_id = ? GROUP BY {column} "
        "ORDER BY total_cost DESC"
    )
    db_rows = conn.execute(query, (params.project_id,)).fetchall()  # type: ignore[union-attr]
    data = [dict(r) for r in db_rows]
    return {
        "group_by": column,
        "data": data,
        "totals": {
            "total_cost_usd": sum(r["total_cost"] for r in data),
            "total_tokens": sum(r["total_tokens"] for r in data),
            "total_calls": sum(r["call_count"] for r in data),
        },
    }


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def forecost_get_cost_summary(
    project_id: int,
    group_by: Literal["day", "model", "provider"] | None = "day",
    days: int | None = None,
) -> str:
    """Get aggregated cost summary for a project, grouped by day, model, or provider."""
    try:
        params = CostSummaryInput(project_id=project_id, group_by=group_by, days=days)
        conn = get_or_create_db()

        if params.group_by == "day":
            result = _summarize_by_day(params, conn)
        else:
            result = _summarize_by_column(params, conn, params.group_by or "model")

        return json.dumps(result, indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}. Use forecost_list_projects to check valid project IDs."
    except sqlite3.Error as e:
        return f"Error: Database error — {e}. Ensure ForeCost is initialized (run 'forecost init')."
    except Exception as e:
        return f"Error: Unexpected error ({type(e).__name__}): {e}"


# ---------------------------------------------------------------------------
# Tool 3: forecost_get_forecast
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def forecost_get_forecast(project_id: int) -> str:
    """Get a cost forecast for a project including projections, confidence, and model diagnostics."""  # noqa: E501
    try:
        params = ForecastInput(project_id=project_id)
        forecaster = ProjectForecaster(params.project_id)
        result = forecaster.calculate_forecast(save=False)
        return json.dumps(result, indent=2, default=str)
    except ValueError:
        return (
            f"Error: Project {project_id} not found. "
            "Use forecost_list_projects to see available projects."
        )
    except sqlite3.Error as e:
        return f"Error: Database error — {e}. Ensure ForeCost is initialized (run 'forecost init')."
    except Exception as e:
        return f"Error: Unexpected error ({type(e).__name__}): {e}"


# ---------------------------------------------------------------------------
# Tool 4: forecost_get_anomalies
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def forecost_get_anomalies(project_id: int) -> str:
    """Detect spending anomalies and budget drift for a project."""
    try:
        params = AnomalyInput(project_id=project_id)
        forecaster = ProjectForecaster(params.project_id)
        result = forecaster.calculate_forecast(save=False)

        drift_status: str = result["drift_status"]
        smoothed_burn_ratio: float = result["smoothed_burn_ratio"]
        confidence: str = result["confidence"]
        actual_spend: float = result["actual_spend"]
        projected_total: float = result["projected_total"]
        baseline_total_cost: float = result["baseline_total_cost"]
        model_breakdown: list[dict] = result["model_breakdown"]

        overshoot_pct: float | None = None
        if baseline_total_cost > 0:
            overshoot_pct = (projected_total - baseline_total_cost) / baseline_total_cost * 100

        if drift_status == "over_budget":
            if overshoot_pct is not None:
                recommendation = (
                    f"Spending is {overshoot_pct:.0f}% over baseline. "
                    "Consider switching to lower-tier models or reducing call frequency."
                )
            else:
                recommendation = (
                    "Spending exceeds baseline. "
                    "Consider switching to lower-tier models or reducing call frequency."
                )
        elif drift_status == "under_budget":
            recommendation = (
                "Spending is significantly under baseline. Your estimates may be too conservative."
            )
        else:
            recommendation = "No anomalies detected. Spending is within expected range."

        report = {
            "project_id": params.project_id,
            "drift_status": drift_status,
            "smoothed_burn_ratio": smoothed_burn_ratio,
            "confidence": confidence,
            "actual_spend": actual_spend,
            "projected_total": projected_total,
            "baseline_total_cost": baseline_total_cost,
            "overshoot_pct": overshoot_pct,
            "recommendation": recommendation,
            "model_breakdown": model_breakdown,
        }
        return json.dumps(report, indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}. Use forecost_list_projects to check valid project IDs."
    except sqlite3.Error as e:
        return f"Error: Database error — {e}. Ensure ForeCost is initialized (run 'forecost init')."
    except Exception as e:
        return f"Error: Unexpected error ({type(e).__name__}): {e}"


# ---------------------------------------------------------------------------
# Tool 5: forecost_get_recent_calls
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
def forecost_get_recent_calls(project_id: int, limit: int | None = 20) -> str:
    """Get recent API call logs for a project."""
    try:
        params = RecentCallsInput(project_id=project_id, limit=limit)
        rows = get_recent_usage_logs(params.project_id, params.limit or 20)
        return json.dumps(rows, indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}. Use forecost_list_projects to check valid project IDs."
    except sqlite3.Error as e:
        return f"Error: Database error — {e}. Ensure ForeCost is initialized (run 'forecost init')."
    except Exception as e:
        return f"Error: Unexpected error ({type(e).__name__}): {e}"


# ---------------------------------------------------------------------------
# Tool 6: forecost_track_call
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
def forecost_track_call(
    project_id: int,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float | None = None,
) -> str:
    """Log an LLM API call to ForeCost's usage database."""
    try:
        params = TrackCallInput(
            project_id=project_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        final_cost = params.cost_usd
        if final_cost is None:
            final_cost = calculate_cost(params.model, params.tokens_in, params.tokens_out)

        provider = get_provider(params.model)

        conn = get_or_create_db()
        row = conn.execute("SELECT id FROM projects WHERE id = ?", (params.project_id,)).fetchone()
        if row is None:
            return (
                f"Error: Project {params.project_id} not found. "
                "Use forecost_list_projects to see available projects."
            )

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO usage_logs "
            "(project_id, timestamp, model, provider, tokens_in, tokens_out, cost_usd, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                params.project_id,
                now,
                params.model,
                provider,
                params.tokens_in,
                params.tokens_out,
                final_cost,
                "mcp",
            ),
        )
        conn.commit()

        record = {
            "project_id": params.project_id,
            "timestamp": now,
            "model": params.model,
            "provider": provider,
            "tokens_in": params.tokens_in,
            "tokens_out": params.tokens_out,
            "cost_usd": final_cost,
            "source": "mcp",
        }
        return json.dumps(record, indent=2, default=str)
    except ValueError as e:
        return f"Error: {e}. Use forecost_list_projects to check valid project IDs."
    except sqlite3.Error as e:
        return f"Error: Database error — {e}. Ensure ForeCost is initialized (run 'forecost init')."
    except Exception as e:
        return f"Error: Unexpected error ({type(e).__name__}): {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the forecost-mcp console script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
