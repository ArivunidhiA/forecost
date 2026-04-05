"""Shared formatting helpers for CLI commands."""

from __future__ import annotations

from rich.text import Text

DRIFT_LABELS: dict[str, tuple[str, str]] = {
    "over_budget": ("Over Budget", "red bold"),
    "under_budget": ("Under Budget", "yellow"),
    "on_track": ("On Track", "green"),
}


def format_drift_text(status: str) -> Text:
    """Return a Rich Text object for the given drift status."""
    label, style = DRIFT_LABELS.get(status, (status, "dim"))
    return Text(label, style=style)


def format_drift_plain(status: str) -> str:
    """Return a plain string label for the given drift status."""
    label, _ = DRIFT_LABELS.get(status, (status, ""))
    return label
