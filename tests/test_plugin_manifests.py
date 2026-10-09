"""Plugin manifests are valid JSON and versions stay in sync (deep-audit FC-009)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def test_plugin_and_package_versions_agree():
    plugin = _load_json("plugin/.claude-plugin/plugin.json")
    from forecost import __version__
    from forecost.version import __version__ as source_version

    assert plugin["version"] == source_version == __version__


def test_hooks_json_is_valid_and_uses_documented_vars():
    hooks = _load_json("plugin/hooks/hooks.json")["hooks"]
    # No lifecycle hook may install packages; SessionStart uses only the
    # shared fail-open launcher after the user explicitly installs Forecost.
    cmds = [h["command"] for h in hooks["SessionStart"][0]["hooks"]]
    assert all("bootstrap.sh" not in c for c in cmds)
    assert any("CLAUDE_PLUGIN_ROOT" in c and "run-hook.sh session-start" in c for c in cmds)
    for groups in hooks.values():
        for group in groups:
            for hook in group["hooks"]:
                assert "bootstrap.sh" not in hook["command"]
                assert "run-hook.sh" in hook["command"]
    # Stop is async (documented field).
    assert hooks["Stop"][0]["hooks"][0]["async"] is True


def test_marketplace_json_is_valid():
    mkt = _load_json(".claude-plugin/marketplace.json")
    assert mkt["name"] == "forecost"
    assert mkt["plugins"][0]["source"] == "./plugin"


def test_bootstrap_is_disabled_and_never_resolves_runtime_packages():
    boot = (ROOT / "plugin/scripts/bootstrap.sh").read_text(encoding="utf-8")
    plugin = _load_json("plugin/.claude-plugin/plugin.json")
    assert f'PLUGIN_VERSION="{plugin["version"]}"' in boot
    assert "exit 0" in boot
    assert "pip install" not in boot
    assert "uv pip" not in boot
    assert "INSTALL_SPEC" not in boot
    assert "git+" not in boot
    assert "@main" not in boot


def _write_hook(path: Path, marker: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\nprintf '%s' \"$1\" > {marker!s}\n", encoding="utf-8")
    path.chmod(0o700)


def _run_launcher(data_dir: Path, hook_name: str = "session-start", *, path: str | None = None):
    environment = {
        **os.environ,
        "CLAUDE_PLUGIN_DATA": str(data_dir),
        "PATH": path if path is not None else os.environ.get("PATH", ""),
    }
    return subprocess.run(  # noqa: S603 - fixed repository script; hook name is a test fixture
        [str(ROOT / "plugin/scripts/run-hook.sh"), hook_name],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh hook launcher")
def test_launcher_uses_only_exact_owned_plugin_environment(tmp_path):
    data = tmp_path / "data"
    hook = data / "venv" / "bin" / "forecost-hook"
    marker = tmp_path / "exact-called"
    _write_hook(hook, marker)

    result = _run_launcher(data)

    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8") == "session-start"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh hook launcher")
def test_launcher_never_falls_back_to_path(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    attacker = tmp_path / "attacker" / "forecost-hook"
    marker = tmp_path / "path-called"
    _write_hook(attacker, marker)

    search_path = os.pathsep.join((str(attacker.parent), os.environ.get("PATH", "")))
    result = _run_launcher(data, path=search_path)

    assert result.returncode == 0
    assert not marker.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh hook launcher")
def test_launcher_rejects_symlinked_or_group_writable_environment(tmp_path):
    actual = tmp_path / "actual-venv"
    marker = tmp_path / "unsafe-called"
    _write_hook(actual / "bin" / "forecost-hook", marker)
    data = tmp_path / "data"
    data.mkdir()
    (data / "venv").symlink_to(actual, target_is_directory=True)

    assert _run_launcher(data).returncode == 0
    assert not marker.exists()

    (data / "venv").unlink()
    hook = data / "venv" / "bin" / "forecost-hook"
    _write_hook(hook, marker)
    (data / "venv").chmod(0o777)

    assert _run_launcher(data).returncode == 0
    assert not marker.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh hook launcher")
def test_launcher_rejects_symlinked_data_parent(tmp_path):
    actual_parent = tmp_path / "actual-parent"
    marker = tmp_path / "unsafe-parent-called"
    _write_hook(actual_parent / "data" / "venv" / "bin" / "forecost-hook", marker)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(actual_parent, target_is_directory=True)

    assert _run_launcher(linked_parent / "data").returncode == 0
    assert not marker.exists()
