"""Trust/privacy hardening: private file permissions and repo-local policy trust."""

import os
import stat
from pathlib import Path

import pytest

from forecost.core.errlog import log_error
from forecost.core.paths import (
    OWNERSHIP_MARKER,
    UnownedDataRootError,
    chmod_private,
    ensure_private_dir,
    forecost_home,
)
from forecost.hooks.handlers import _policy_path

_POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")


@_POSIX_ONLY
def test_ensure_private_dir_is_owner_only(tmp_path):
    d = tmp_path / "home"
    ensure_private_dir(d)
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    # Idempotent even if the dir already existed with looser perms.
    d.chmod(0o755)
    ensure_private_dir(d)
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


@_POSIX_ONLY
def test_chmod_private_locks_a_file(tmp_path):
    f = tmp_path / "secret.db"
    f.write_text("x")
    f.chmod(0o644)
    chmod_private(f)
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


@_POSIX_ONLY
def test_existing_unowned_directory_is_not_claimed_or_chmodded(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    (shared / "unrelated.txt").write_text("keep")

    ensure_private_dir(shared)

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert not (shared / OWNERSHIP_MARKER).exists()


def test_ledger_refuses_nonempty_unowned_custom_home(tmp_path, monkeypatch):
    from forecost.ledger import db as ledger_db

    custom = tmp_path / "shared"
    custom.mkdir()
    (custom / "unrelated.txt").write_text("keep")
    monkeypatch.setenv("FORECOST_HOME", str(custom))
    monkeypatch.setattr(ledger_db, "LEDGER_PATH", custom / "ledger.db")
    ledger_db.reset_connection_for_tests()

    with pytest.raises(UnownedDataRootError, match="ownership marker"):
        ledger_db.get_ledger_db()

    assert sorted(path.name for path in custom.iterdir()) == ["unrelated.txt"]
    ledger_db.reset_connection_for_tests()


def test_legacy_db_refuses_nonempty_unowned_custom_home(tmp_path, monkeypatch):
    import forecost.db as legacy_db

    custom = tmp_path / "shared-legacy"
    custom.mkdir(mode=0o755)
    unrelated = custom / "unrelated.txt"
    unrelated.write_text("keep")
    before_mode = stat.S_IMODE(custom.stat().st_mode)
    monkeypatch.setenv("FORECOST_HOME", str(custom))
    monkeypatch.setattr(legacy_db, "_conn", None)

    with pytest.raises(UnownedDataRootError, match="ownership marker"):
        legacy_db.get_or_create_db()

    assert sorted(path.name for path in custom.iterdir()) == ["unrelated.txt"]
    assert unrelated.read_text() == "keep"
    assert stat.S_IMODE(custom.stat().st_mode) == before_mode
    legacy_db._conn = None


def test_forecost_home_rejects_relative_override(monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", "relative/data")
    with pytest.raises(ValueError, match="absolute"):
        forecost_home()


@_POSIX_ONLY
def test_error_log_is_written_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    log_error("test", "something went wrong")
    log_file = tmp_path / "error.log"
    assert log_file.exists()
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600


@_POSIX_ONLY
def test_legacy_database_honors_forecost_home_and_is_private(tmp_path, monkeypatch):
    import forecost.db as legacy_db

    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "private-home"))
    monkeypatch.setattr(legacy_db, "_conn", None)
    conn = legacy_db.get_or_create_db()
    db_path = tmp_path / "private-home" / "costs.db"
    try:
        assert db_path.exists()
        assert stat.S_IMODE(db_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
    finally:
        conn.close()
        legacy_db._conn = None


def test_repo_local_policy_is_untrusted_by_default(tmp_path, monkeypatch):
    """A repo-local .forecost.toml must not govern enforcement unless the user
    explicitly opts in — a hostile clone could otherwise gate the session."""
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FORECOST_TRUST_PROJECT_POLICY", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".forecost.toml").write_text(
        '[[policy.rules]]\nid="evil"\nscope="session"\nhard_limit=0.0\naction="deny"\n'
    )

    # Default: home policy governs, repo file ignored.
    assert _policy_path(str(repo)) == Path(tmp_path / "home") / "policy.toml"

    # Opt in: repo policy is honored.
    monkeypatch.setenv("FORECOST_TRUST_PROJECT_POLICY", "1")
    assert _policy_path(str(repo)) == repo / ".forecost.toml"
