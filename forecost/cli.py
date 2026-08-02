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

_CURRENT_COMMANDS: dict[str, _LazyCommand] = {
    "burn": ("forecost.commands.burn_cmd", "burn", "Show trailing spend and budget runway."),
    "calibration": (
        "forecost.commands.calibration_cmd",
        "calibration",
        "Inspect shadow-estimator calibration.",
    ),
    "doctor": ("forecost.commands.doctor_cmd", "doctor", "Inspect local setup and paths."),
    "envelope": (
        "forecost.commands.envelope_cmd",
        "envelope",
        "Manage experimental local resource envelopes.",
    ),
    "ingest": ("forecost.commands.ingest_cmd", "ingest", "Ingest agent usage into the ledger."),
    "ledger": ("forecost.commands.ledger_cmd", "ledger", "Inspect the local usage ledger."),
    "lab": ("forecost.commands.lab_cmd", "lab", "Run deterministic offline receipt scenarios."),
    "mark": (
        "forecost.commands.mark_cmd",
        "mark",
        "Record explicit, content-free outcome evidence.",
    ),
    "migrate": ("forecost.commands.migrate_cmd", "migrate", "Migrate legacy usage once."),
    "pricing-audit": (
        "forecost.commands.pricing_audit_cmd",
        "pricing_audit",
        "Find guessed or stale pricing.",
    ),
    "privacy": ("forecost.commands.privacy_cmd", "privacy", "Inspect local privacy boundaries."),
    "purge": ("forecost.commands.purge_cmd", "purge", "Safely remove Forecost-owned data."),
    "reconcile": (
        "forecost.commands.reconcile_cmd",
        "reconcile",
        "Compare independent ledger valuations.",
    ),
    "receipt": (
        "forecost.commands.receipt_cmd",
        "receipt",
        "Render or compare graph-aware receipts.",
    ),
    "recover": (
        "forecost.commands.recover_cmd",
        "recover",
        "Replay durable failed-write records.",
    ),
    "runs": ("forecost.commands.runs_cmd", "runs", "List and inspect graph-aware agent runs."),
    "self-test": (
        "forecost.commands.self_test_cmd",
        "self_test",
        "Run deterministic local integration checks.",
    ),
    "setup": (
        "forecost.commands.setup_cmd",
        "setup",
        "Prepare integrations without host mutation.",
    ),
    "verify": ("forecost.commands.verify_cmd", "verify", "Verify receipt snapshot integrity."),
}

_LEGACY_COMMANDS: dict[str, _LazyCommand] = {
    "calc": ("forecost.commands.calc_cmd", "calc", "Calculate model costs for a prompt."),
    "demo": ("forecost.commands.demo_cmd", "demo", "Run the legacy forecast demo."),
    "export": ("forecost.commands.export_cmd", "export_data", "Export legacy usage data."),
    "forecast": (
        "forecost.commands.forecast_cmd",
        "forecast",
        "Run the legacy calendar-spend forecast.",
    ),
    "init": ("forecost.commands.init_cmd", "init", "Initialize legacy project tracking."),
    "optimize": (
        "forecost.commands.optimize_cmd",
        "optimize",
        "Suggest legacy model-cost alternatives.",
    ),
    "price": ("forecost.commands.price_cmd", "price", "Browse bundled model pricing."),
    "reset": ("forecost.commands.reset_cmd", "reset", "Reset legacy project state."),
    "serve": ("forecost.commands.serve_cmd", "serve", "Run the legacy local API."),
    "status": ("forecost.commands.status_cmd", "status", "Show legacy project status."),
    "track": ("forecost.commands.track_cmd", "track", "Show recent legacy usage."),
    "watch": ("forecost.commands.watch_cmd", "watch", "Watch legacy project spend."),
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
        # Compatibility aliases deliberately do not appear in root help.  They
        # keep existing scripts alive until 1.0 while `forecost legacy ...`
        # makes the retirement boundary explicit for humans and new docs.
        if spec is None:
            spec = _LEGACY_COMMANDS.get(cmd_name)
        if spec is None:
            return None
        module_name, attribute, _help = spec
        loaded = getattr(importlib.import_module(module_name), attribute)
        if not isinstance(loaded, click.Command):
            raise TypeError(f"{module_name}.{attribute} is not a Click command")
        return loaded

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rows = [(name, _CURRENT_COMMANDS[name][2]) for name in _CURRENT_COMMANDS]
        rows.append(("legacy", "Compatibility commands scheduled for removal before 1.0."))
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
        module_name, attribute, _help = spec
        loaded = getattr(importlib.import_module(module_name), attribute)
        if not isinstance(loaded, click.Command):
            raise TypeError(f"{module_name}.{attribute} is not a Click command")
        return loaded

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        with formatter.section("Legacy commands"):
            formatter.write_dl([(name, spec[2]) for name, spec in _LEGACY_COMMANDS.items()])


@click.group(cls=LazyGroup)
@click.version_option(__version__, "--version", prog_name="forecost")
def main() -> None:
    """Local, content-free evidence receipts for AI-agent runs."""


@main.group("legacy", cls=LazyLegacyGroup)
def legacy() -> None:
    """v0.2 calendar-forecast compatibility surface; removed before 1.0."""
