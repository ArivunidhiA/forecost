from __future__ import annotations

import re
from pathlib import Path

import click
from rich.console import Console

from forecost.core.local_identity import INSTALLATION_KEY_ID_NAME, INSTALLATION_KEY_NAME
from forecost.core.paths import OWNERSHIP_MARKER, forecost_home

console = Console()

# Purge is intentionally an allow-list, not ``rmtree(forecost_home())``. An
# operator can relocate FORECOST_HOME, so recursively deleting that path would
# turn a typo (or a malicious environment) into deletion of unrelated data.
_OWNED_NAMES = frozenset(
    {
        "ledger.db",
        "ledger.db-wal",
        "ledger.db-shm",
        "ledger.db-journal",
        "costs.db",
        "costs.db-wal",
        "costs.db-shm",
        "costs.db-journal",
        "error.log",
        INSTALLATION_KEY_NAME,
        INSTALLATION_KEY_ID_NAME,
        "policy.toml",
        "recovery.jsonl",
        "recovery.replayed.jsonl",
        "legacy-recovery.jsonl",
        "legacy-recovery.replayed.jsonl",
        OWNERSHIP_MARKER,
    }
)

# Owned subdirectories are purged one manifest entry at a time.  Unknown files
# or nested directories are preserved, and no recursive deletion primitive is
# used.  This covers the durable files emitted by hooks/state.py and the
# default LiteLLM DurableEventOutbox.
_OWNED_DIRECTORY_FILES = {
    "hooks": frozenset(
        {
            OWNERSHIP_MARKER,
            "heartbeat.json",
            "last-summary.json",
            "settlement-required.jsonl",
        }
    ),
    "outbox": frozenset(
        {
            OWNERSHIP_MARKER,
            "litellm.jsonl",
            "litellm.jsonl.lock",
            "litellm.jsonl.poison.jsonl",
            "litellm.jsonl.stats.json",
        }
    ),
}
_OWNED_DIRECTORY_TEMP = {
    "hooks": re.compile(
        r"^\.(?:heartbeat\.json|last-summary\.json|settlement-required\.jsonl)"
        r"\.[A-Za-z0-9_-]{6,}$"
    ),
    "outbox": re.compile(r"^\.litellm\.jsonl(?:\.stats\.json)?\.[A-Za-z0-9_-]{6,}$"),
}
_OWNED_ROOT_TEMP = re.compile(r"^\.(?:legacy-)?recovery(?:-spill)?-[A-Za-z0-9_.-]+\.tmp$")
_SCHEMA_BACKUP = re.compile(
    r"^ledger\.db\.pre-v\d+-\d{8}T\d{12,20}Z\.bak(?:-(?:wal|shm|journal))?$"
)


class UnsafePurgeTarget(ValueError):
    """Raised when FORECOST_HOME is not a safe, dedicated data directory."""


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _resolve_purge_target(home: Path) -> Path:
    if not home.is_absolute():
        raise UnsafePurgeTarget("FORECOST_HOME must be an absolute path")
    if _has_symlink_component(home):
        raise UnsafePurgeTarget("FORECOST_HOME must not contain symlink components")
    return home.resolve(strict=False)


def _validate_purge_boundaries(target: Path, cwd: Path | None) -> Path:
    workspace = (cwd or Path.cwd()).resolve()
    user_home = Path.home().resolve()
    filesystem_root = Path(target.anchor)
    if target == filesystem_root:
        raise UnsafePurgeTarget("FORECOST_HOME cannot be a filesystem root")
    if target == user_home or target in user_home.parents:
        raise UnsafePurgeTarget("FORECOST_HOME cannot be the user home or one of its ancestors")
    if target == workspace or target in workspace.parents:
        raise UnsafePurgeTarget("FORECOST_HOME cannot be the current workspace or an ancestor")
    return user_home


def _validate_purge_ownership(target: Path, user_home: Path) -> None:
    if target.exists() and not target.is_dir():
        raise UnsafePurgeTarget("FORECOST_HOME exists but is not a directory")
    if target.exists() and target != user_home / ".forecost":
        marker = target / OWNERSHIP_MARKER
        if not marker.is_file() or marker.is_symlink():
            raise UnsafePurgeTarget("custom FORECOST_HOME has no Forecost ownership marker")


def _validated_home(home: Path, cwd: Path | None = None) -> Path:
    """Return an absolute purge target or refuse broad/symlinked locations."""
    target = _resolve_purge_target(home)
    user_home = _validate_purge_boundaries(target, cwd)
    _validate_purge_ownership(target, user_home)
    return target


def _is_owned_entry(path: Path) -> bool:
    name = path.name
    spool = re.fullmatch(r"(?:legacy-)?recovery\.\d+\.\d+\.[0-9a-f]{32}\.jsonl", name)
    replayed = re.fullmatch(
        r"(?:legacy-)?recovery(?:\.\d+\.\d+\.[0-9a-f]{32})?"
        r"\.replayed(?:\.\d+)?\.jsonl",
        name,
    )
    return (
        name in _OWNED_NAMES
        or spool is not None
        or replayed is not None
        or _OWNED_ROOT_TEMP.fullmatch(name) is not None
        or _SCHEMA_BACKUP.fullmatch(name) is not None
    )


def _is_owned_directory_file(directory: str, name: str) -> bool:
    return name in _OWNED_DIRECTORY_FILES[directory] or bool(
        _OWNED_DIRECTORY_TEMP[directory].fullmatch(name)
    )


def _delete_owned_directory(entry: Path, removed: list[str], preserved: list[str]) -> None:
    if entry.is_symlink():
        entry.unlink()
        removed.append(str(entry))
        return
    if not entry.is_dir():
        preserved.append(str(entry))
        return
    for child in entry.iterdir():
        if not _is_owned_directory_file(entry.name, child.name) or (
            child.is_dir() and not child.is_symlink()
        ):
            preserved.append(str(child))
            continue
        child.unlink()
        removed.append(str(child))
    try:
        entry.rmdir()
        removed.append(str(entry))
    except OSError:
        pass


def _delete_entry(entry: Path, removed: list[str], preserved: list[str]) -> None:
    if entry.name in _OWNED_DIRECTORY_FILES:
        _delete_owned_directory(entry, removed, preserved)
        return
    if not _is_owned_entry(entry) or (entry.is_dir() and not entry.is_symlink()):
        preserved.append(str(entry))
        return
    # unlinking a known-name symlink removes the link, never its target.
    entry.unlink()
    removed.append(str(entry))


def _purge_data_home(home: Path) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    preserved: list[str] = []
    if not home.exists():
        return removed, preserved
    if not home.is_dir():
        raise UnsafePurgeTarget("FORECOST_HOME exists but is not a directory")
    for entry in home.iterdir():
        _delete_entry(entry, removed, preserved)
    try:
        home.rmdir()  # only succeeds when no unknown/user-owned entries remain
        removed.append(str(home))
    except OSError:
        pass
    return removed, preserved


def _purge_local_config(keep_config: bool) -> list[str]:
    local_toml = Path.cwd() / ".forecost.toml"
    if keep_config or not (local_toml.is_file() or local_toml.is_symlink()):
        return []
    local_toml.unlink()
    return [str(local_toml)]


def _collect_and_delete(keep_config: bool) -> tuple[list[str], list[str]]:
    """Delete only known Forecost files, returning (removed, preserved)."""
    home = _validated_home(forecost_home())
    removed, preserved = _purge_data_home(home)
    removed.extend(_purge_local_config(keep_config))
    return removed, preserved


def _report(removed: list[str], preserved: list[str]) -> None:
    if not removed:
        console.print("[yellow]Nothing to purge.[/yellow] No forecost data found.")
    else:
        for path in removed:
            console.print(f"  [red]Deleted[/red] {path}")
    if preserved:
        console.print("\n[yellow]Preserved unknown entries:[/yellow]")
        for path in preserved:
            console.print(f"  {path}")
    if preserved:
        console.print(
            "\n[yellow]Known-file purge finished, but retained entries remain.[/yellow] "
            "Review the paths above and docs/data-inventory.md before reusing this home."
        )
    else:
        console.print(
            "\n[green]Known-file purge finished.[/green] This does not prove that "
            "integration backups, exports, or other owned state outside this root were erased."
        )


def _confirm_prompt() -> str:
    return (
        f"This deletes known Forecost data files at {forecost_home()} — including "
        "ledger.db (your entire spend + calibration history, which cannot be "
        "recovered), costs.db, error.log, and recovery.jsonl. Unknown files and "
        "directories are preserved. Continue?"
    )


@click.command()
@click.option("--keep-config", is_flag=True, help="Keep .forecost.toml in the current directory")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def purge(keep_config: bool, yes: bool) -> None:
    """Remove known Forecost data from this machine.

    Deletes only allow-listed Forecost files inside $FORECOST_HOME or
    ~/.forecost and optionally .forecost.toml in the current directory. It
    refuses broad, relative, or symlinked data roots and never recursively
    deletes unknown content.
    """
    try:
        _validated_home(forecost_home())
    except (UnsafePurgeTarget, ValueError) as exc:
        raise click.ClickException(f"Refusing unsafe purge target: {exc}") from exc
    if not yes and not click.confirm(_confirm_prompt()):
        console.print("[yellow]Aborted.[/yellow] Nothing was deleted.")
        return
    try:
        removed, preserved = _collect_and_delete(keep_config)
    except (UnsafePurgeTarget, ValueError) as exc:
        raise click.ClickException(f"Refusing unsafe purge target: {exc}") from exc
    _report(removed, preserved)
