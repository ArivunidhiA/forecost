"""Strict matched-run economic/outcome comparison or diagnostic abstention."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import click

from forecost.comparison import (
    ComparisonConfigurationError,
    compare_manifests,
    compare_runs_diagnostic,
    comparison_exit_code,
    comparison_text,
    validate_comparison_inputs,
    validate_diagnostic_inputs,
)
from forecost.core.paths import UnsafeDataPathError
from forecost.ledger.db import get_readonly_ledger_db

_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_DIAGNOSTIC_AUTHORITIES = (
    "list_rate",
    "gateway_estimate",
    "provider_estimate",
    "user_imported_claim",
)


class CompareCommand(click.Command):
    """Use exit 64 for parser/configuration errors in this command contract."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        try:
            return cast(list[str], super().parse_args(ctx, args))
        except click.UsageError as error:
            error.exit_code = 64
            raise


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComparisonConfigurationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_integer_number(_value: str) -> object:
    raise ComparisonConfigurationError("comparison JSON must use finite integer numbers")


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            raw = stream.read(_MAX_MANIFEST_BYTES + 1)
        if len(raw) > _MAX_MANIFEST_BYTES:
            raise ComparisonConfigurationError(f"{label} file exceeds 8 MiB")
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_float=_reject_non_integer_number,
            parse_constant=_reject_non_integer_number,
        )
    except (OSError, UnicodeError) as error:
        raise ComparisonConfigurationError(f"could not read {label} as UTF-8 JSON") from error
    except json.JSONDecodeError as error:
        raise ComparisonConfigurationError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ComparisonConfigurationError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _render(result: dict[str, object], *, json_output: bool, markdown: bool) -> None:
    if json_output:
        click.echo(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        click.echo(comparison_text(result, markdown=markdown), nl=False)


def _diagnostic_result(
    baseline: str,
    candidate: str,
    *,
    authority: str | None,
    currency: str | None,
    line_items: tuple[str, ...],
) -> dict[str, object]:
    diagnostic_authority = authority or "list_rate"
    diagnostic_currency = currency or "USD"
    diagnostic_line_items = line_items or ("model_inference",)
    validate_diagnostic_inputs(
        baseline,
        candidate,
        authority=diagnostic_authority,
        currency=diagnostic_currency,
        line_items=diagnostic_line_items,
    )
    with closing(get_readonly_ledger_db()) as conn:
        return compare_runs_diagnostic(
            conn,
            baseline,
            candidate,
            authority=diagnostic_authority,
            currency=diagnostic_currency,
            line_items=diagnostic_line_items,
        )


def _manifest_result(
    baseline: str,
    candidate: str,
    policy_path: Path,
    *,
    authority: str | None,
    currency: str | None,
    line_items: tuple[str, ...],
) -> dict[str, object]:
    if authority is not None or currency is not None or line_items:
        raise ComparisonConfigurationError(
            "--authority, --currency, and --line-item are diagnostic-only; the policy owns scope"
        )
    baseline_manifest = _load_json_object(Path(baseline), "baseline manifest")
    candidate_manifest = _load_json_object(Path(candidate), "candidate manifest")
    policy = _load_json_object(policy_path, "comparison policy")
    validate_comparison_inputs(baseline_manifest, candidate_manifest, policy)
    with closing(get_readonly_ledger_db()) as conn:
        return compare_manifests(conn, baseline_manifest, candidate_manifest, policy)


@click.command(cls=CompareCommand)
@click.argument("baseline")
@click.argument("candidate")
@click.option(
    "--profile",
    type=click.Choice(["economic-outcome"]),
    default="economic-outcome",
    show_default=True,
)
@click.option(
    "--policy",
    "policy_path",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Evaluate two compare-arm JSON manifests under this predeclared policy.",
)
@click.option(
    "--authority",
    type=click.Choice(_DIAGNOSTIC_AUTHORITIES),
    default=None,
    help="Diagnostic authority; a full comparison declares this in --policy.",
)
@click.option(
    "--currency",
    type=click.Choice(["USD"]),
    default=None,
    help="Diagnostic currency; v1 performs no FX conversion.",
)
@click.option(
    "--line-item",
    "line_items",
    type=click.Choice(["model_inference", "tool_call"]),
    multiple=True,
    help="Diagnostic economic line; repeat to select more than one.",
)
@click.option("--json-output", is_flag=True, help="Emit deterministic JSON.")
@click.option("--markdown", is_flag=True, help="Render the same result as Markdown.")
@click.pass_context
def compare(
    ctx: click.Context,
    baseline: str,
    candidate: str,
    profile: str,
    policy_path: Path | None,
    authority: str | None,
    currency: str | None,
    line_items: tuple[str, ...],
    json_output: bool,
    markdown: bool,
) -> None:
    """Compare matched manifests, or diagnose why two RUN_IDs cannot qualify.

    Without --policy, BASELINE and CANDIDATE are canonical run identifiers. The
    command reports an authority-specific descriptive delta but deliberately
    abstains: two receipts do not prove matched workload or outcome identity.

    With --policy, BASELINE and CANDIDATE are compare-arm JSON manifest paths.
    The policy predeclares the exact case roster, estimator basis, external
    outcome binding, and abstention thresholds. Output is observational; it is
    never a causal savings or provider-billing claim.
    """
    del profile  # the only supported versioned profile is frozen by Click
    if json_output and markdown:
        click.echo("error: --json-output and --markdown cannot be used together", err=True)
        ctx.exit(64)
    try:
        if policy_path is None:
            result = _diagnostic_result(
                baseline,
                candidate,
                authority=authority,
                currency=currency,
                line_items=line_items,
            )
        else:
            result = _manifest_result(
                baseline,
                candidate,
                policy_path,
                authority=authority,
                currency=currency,
                line_items=line_items,
            )
    except ComparisonConfigurationError as error:
        click.echo(f"configuration error: {error}", err=True)
        ctx.exit(64)
    except (OSError, sqlite3.Error, UnsafeDataPathError) as error:
        click.echo(f"internal comparison error: {error}", err=True)
        ctx.exit(5)
    except Exception:
        click.echo("internal comparison error; no decision was produced", err=True)
        ctx.exit(5)
    _render(result, json_output=json_output, markdown=markdown)
    ctx.exit(comparison_exit_code(result))
