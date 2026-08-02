import subprocess
import sys
from pathlib import Path

from scripts.check_release import check_release, release_versions

ROOT = Path(__file__).resolve().parent.parent


def test_all_release_versions_agree():
    versions = release_versions()
    assert len(set(versions.values())) == 1
    version = next(iter(versions.values()))
    assert check_release() == version


def test_release_check_cli_rejects_wrong_tag():
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(ROOT / "scripts/check_release.py"), "--tag", "v0.0.0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "must equal" in result.stderr


def test_release_check_rejects_unreleased_changelog():
    version = next(iter(release_versions().values()))
    result = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(ROOT / "scripts/check_release.py"), "--tag", f"v{version}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "still marks" in result.stderr
