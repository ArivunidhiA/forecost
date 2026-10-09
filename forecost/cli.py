"""Command-line entrypoint with lazy command imports.

Ledger commands should not pay the import cost of the deprecated forecasting
stack (NumPy/statsmodels). The static help text also keeps ``forecost --help``
cheap while each selected command remains a normal Click command.
"""

from __future__ import annotations

import importlib

import click

from forecost import __version__

_LazyCommand = tuple[str, str, str, str]

_CURRENT_COMMANDS: dict[str, _LazyCommand] = {
    "adapters": (
        "forecost.commands.adapters_cmd",
        "adapters",
        "Inspect adapter protocol conformance.",
        "no persistent store (offline conformance)",
    ),
    "burn": (
        "forecost.commands.burn_cmd",
        "burn",
        "Show trailing observed spend and runway.",
        "canonical ledger.db (read-only)",
    ),
    "calibration": (
        "forecost.commands.calibration_cmd",
        "calibration",
        "Inspect shadow-estimator calibration.",
        "canonical ledger.db (read-only)",
    ),
    "capture": (
        "forecost.commands.capture_cmd",
        "capture",
        "Record bounded local test/build exit evidence.",
        "canonical ledger.db",
    ),
    "compare": (
        "forecost.commands.compare_cmd",
        "compare",
        "Compare matched economic/outcome evidence or explain why it cannot qualify.",
        "canonical ledger.db (read-only); optional caller-selected JSON manifests",
    ),
    "doctor": (
        "forecost.commands.doctor_cmd",
        "doctor",
        "Inspect local setup, stores, and evidence boundaries.",
        "canonical ledger.db (read-only); observes legacy costs.db presence",
    ),
    "envelope": (
        "forecost.commands.envelope_cmd",
        "envelope",
        "Manage experimental local resource envelopes.",
        "canonical ledger.db",
    ),
    "ingest": (
        "forecost.commands.ingest_cmd",
        "ingest",
        "Ingest local runtime observations.",
        "canonical ledger.db",
    ),
    "import": (
        "forecost.commands.import_cmd",
        "import_data",
        "Import offline runtime evidence.",
        "canonical ledger.db",
    ),
    "ledger": (
        "forecost.commands.ledger_cmd",
        "ledger",
        "Inspect or migrate the canonical ledger.",
        "canonical ledger.db",
    ),
    "lab": (
        "forecost.commands.lab_cmd",
        "lab",
        "Run deterministic offline receipt scenarios.",
        "explicit isolated ledger.db",
    ),
    "mark": (
        "forecost.commands.mark_cmd",
        "mark",
        "Record explicit, bounded outcome evidence.",
        "canonical ledger.db",
    ),
    "migrate": (
        "forecost.commands.migrate_cmd",
        "migrate",
        "Copy legacy observations without elevating their authority.",
        "reads legacy costs.db; appends canonical ledger.db",
    ),
    "pricing-audit": (
        "forecost.commands.pricing_audit_cmd",
        "pricing_audit",
        "Find guessed or stale pricing.",
        "canonical ledger.db (read-only)",
    ),
    "privacy": (
        "forecost.commands.privacy_cmd",
        "privacy",
        "Inspect local privacy boundaries.",
        "Forecost-owned local files (read-only)",
    ),
    "purge": (
        "forecost.commands.purge_cmd",
        "purge",
        "Remove a bounded file allowlist and report retained state.",
        "known FORECOST_HOME files and cwd .forecost.toml; not exports/integration backups",
    ),
    "reconcile": (
        "forecost.commands.reconcile_cmd",
        "reconcile",
        "Compare independent ledger valuations.",
        "canonical ledger.db",
    ),
    "receipt": (
        "forecost.commands.receipt_cmd",
        "receipt",
        "Render or compare graph-aware receipts.",
        "canonical ledger.db (read-only)",
    ),
    "recover": (
        "forecost.commands.recover_cmd",
        "recover",
        "Replay durable failed-write records.",
        "canonical ledger.db and Forecost recovery spools",
    ),
    "runs": (
        "forecost.commands.runs_cmd",
        "runs",
        "List and inspect graph-aware agent runs.",
        "canonical ledger.db (read-only)",
    ),
    "self-test": (
        "forecost.commands.self_test_cmd",
        "self_test",
        "Run deterministic local integration checks.",
        "temporary isolated test data only",
    ),
    "setup": (
        "forecost.commands.setup_cmd",
        "setup",
        "Inspect or reversibly manage integrations; dry-run/check do not mutate.",
        "integration configuration; no ledger writes in dry-run/check mode",
    ),
    "statusline": (
        "forecost.commands.statusline_cmd",
        "statusline",
        "Render Claude hook/evidence health.",
        "canonical ledger.db and hook health files (read-only)",
    ),
    "verify": (
        "forecost.commands.verify_cmd",
        "verify",
        "Verify receipt snapshot integrity.",
        "canonical ledger.db (read-only)",
    ),
}

_LEGACY_COMMANDS: dict[str, _LazyCommand] = {
    "calc": (
        "forecost.commands.calc_cmd",
        "calc",
        "Calculate a legacy list-rate estimate.",
        "no persistent store",
    ),
    "demo": (
        "forecost.commands.demo_cmd",
        "demo",
        "Run the retired forecast demo.",
        "legacy costs.db",
    ),
    "export": (
        "forecost.commands.export_cmd",
        "export_data",
        "Export retired-product usage.",
        "legacy costs.db (read-only)",
    ),
    "forecast": (
        "forecost.commands.forecast_cmd",
        "forecast",
        "Run the legacy calendar-spend forecast.",
        "legacy costs.db",
    ),
    "init": (
        "forecost.commands.init_cmd",
        "init",
        "Initialize retired local-only project tracking.",
        "legacy costs.db and project .forecost.toml",
    ),
    "optimize": (
        "forecost.commands.optimize_cmd",
        "optimize",
        "Suggest legacy model-cost alternatives.",
        "legacy costs.db (read-only)",
    ),
    "price": (
        "forecost.commands.price_cmd",
        "price",
        "Browse bundled legacy model pricing.",
        "no persistent store",
    ),
    "reset": (
        "forecost.commands.reset_cmd",
        "reset",
        "Reset retired project state.",
        "legacy costs.db and project .forecost.toml",
    ),
    "status": (
        "forecost.commands.status_cmd",
        "status",
        "Show retired project status.",
        "legacy costs.db (read-only)",
    ),
    "track": (
        "forecost.commands.track_cmd",
        "track",
        "Show retired-product usage.",
        "legacy costs.db (read-only)",
    ),
    "watch": (
        "forecost.commands.watch_cmd",
        "watch",
        "Watch retired-project spend.",
        "legacy costs.db (read-only)",
    ),
}


class LazyGroup(click.Group):
    """Load only the command selected by the user."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(set(super().list_commands(ctx)) | set(_CURRENT_COMMANDS))

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        spec = _CURRENT_COMMANDS.get(cmd_name)
        if spec is None:
            return None
        module_name, attribute, _help, store = spec
        loaded = getattr(importlib.import_module(module_name), attribute)
        if not isinstance(loaded, click.Command):
            raise TypeError(f"{module_name}.{attribute} is not a Click command")
        loaded.epilog = f"Store boundary: {store}."
        return loaded

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rows = [(name, f"{spec[2]} [store: {spec[3]}]") for name, spec in _CURRENT_COMMANDS.items()]
        rows.append(("legacy", "Unsupported v0.2 compatibility; isolated from ledger.db."))
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


class LazyLegacyGroup(click.Group):
    """Keep the former calendar forecast surface out of the current product path."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(_LEGACY_COMMANDS)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        spec = _LEGACY_COMMANDS.get(cmd_name)
        if spec is None:
            return None
        module_name, attribute, _help, store = spec
        loaded = getattr(importlib.import_module(module_name), attribute)
        if not isinstance(loaded, click.Command):
            raise TypeError(f"{module_name}.{attribute} is not a Click command")
        loaded.epilog = f"Legacy store boundary: {store}. This is not a supported product surface."
        return loaded

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        with formatter.section("Legacy commands"):
            formatter.write_dl(
                [(name, f"{spec[2]} [store: {spec[3]}]") for name, spec in _LEGACY_COMMANDS.items()]
            )


@click.group(cls=LazyGroup)
@click.version_option(__version__, "--version", prog_name="forecost")
def main() -> None:
    """Experimental local, content-minimizing evidence receipts for AI-agent runs."""


@main.group("legacy", cls=LazyLegacyGroup)
def legacy() -> None:
    """Unsupported v0.2 compatibility using costs.db; removed before 1.0."""
