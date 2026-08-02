"""Command-line entrypoint with lazy command imports.

Ledger commands should not pay the import cost of the deprecated forecasting
stack (NumPy/statsmodels). The static help text also keeps ``forecost --help``
cheap while each selected command remains a normal Click command.
"""

from __future__ import annotations

import importlib

import click

from forecost import __version__

_LazyCommand = tuple[str, str, str]

_LAZY_COMMANDS: dict[str, _LazyCommand] = {
    "burn": ("forecost.commands.burn_cmd", "burn", "Show trailing spend and budget runway."),
    "calc": ("forecost.commands.calc_cmd", "calc", "Calculate model costs for a prompt."),
    "calibration": (
        "forecost.commands.calibration_cmd",
        "calibration",
        "Inspect shadow-estimator calibration.",
    ),
    "demo": ("forecost.commands.demo_cmd", "demo", "Run the legacy forecast demo."),
    "doctor": ("forecost.commands.doctor_cmd", "doctor", "Inspect local setup and paths."),
    "export": ("forecost.commands.export_cmd", "export_data", "Export legacy usage data."),
    "forecast": (
        "forecost.commands.forecast_cmd",
        "forecast",
        "Run the legacy calendar-spend forecast.",
    ),
    "ingest": ("forecost.commands.ingest_cmd", "ingest", "Ingest agent usage into the ledger."),
    "init": ("forecost.commands.init_cmd", "init", "Initialize legacy project tracking."),
    "ledger": ("forecost.commands.ledger_cmd", "ledger", "Inspect the local usage ledger."),
    "migrate": ("forecost.commands.migrate_cmd", "migrate", "Migrate legacy usage once."),
    "optimize": (
        "forecost.commands.optimize_cmd",
        "optimize",
        "Suggest legacy model-cost alternatives.",
    ),
    "price": ("forecost.commands.price_cmd", "price", "Browse bundled model pricing."),
    "pricing-audit": (
        "forecost.commands.pricing_audit_cmd",
        "pricing_audit",
        "Find guessed or stale pricing.",
    ),
    "purge": ("forecost.commands.purge_cmd", "purge", "Safely remove Forecost-owned data."),
    "reconcile": (
        "forecost.commands.reconcile_cmd",
        "reconcile",
        "Compare independent ledger valuations.",
    ),
    "recover": (
        "forecost.commands.recover_cmd",
        "recover",
        "Replay durable failed-write records.",
    ),
    "reset": ("forecost.commands.reset_cmd", "reset", "Reset legacy project state."),
    "serve": ("forecost.commands.serve_cmd", "serve", "Run the legacy local API."),
    "status": ("forecost.commands.status_cmd", "status", "Show legacy project status."),
    "track": ("forecost.commands.track_cmd", "track", "Show recent legacy usage."),
    "watch": ("forecost.commands.watch_cmd", "watch", "Watch legacy project spend."),
}


class LazyGroup(click.Group):
    """Load only the command selected by the user."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(set(super().list_commands(ctx)) | set(_LAZY_COMMANDS))

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        spec = _LAZY_COMMANDS.get(cmd_name)
        if spec is None:
            return None
        module_name, attribute, _help = spec
        loaded = getattr(importlib.import_module(module_name), attribute)
        if not isinstance(loaded, click.Command):
            raise TypeError(f"{module_name}.{attribute} is not a Click command")
        return loaded

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rows = [(name, _LAZY_COMMANDS[name][2]) for name in self.list_commands(ctx)]
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


@click.group(cls=LazyGroup)
@click.version_option(__version__, "--version", prog_name="forecost")
def main() -> None:
    """A local, content-free ledger for AI agent work.

    Records what your agents actually cost across harnesses, reconciles the
    meters nobody trusts, and gates budgets via fail-open hooks. INGEST,
    LEDGER, RECONCILE, BURN, and CALIBRATION are the current product.
    """
