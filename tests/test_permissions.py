"""Trust/privacy hardening: private file permissions and repo-local policy trust."""

import os
import stat
from pathlib import Path

import pytest

from forecost.core.errlog import log_error
from forecost.core.paths import chmod_private, ensure_private_dir
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
def test_error_log_is_written_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    log_error("test", "something went wrong")
    log_file = tmp_path / "error.log"
    assert log_file.exists()
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600


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
