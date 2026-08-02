"""Fail a release when its immutable version surfaces disagree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def _match_version(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"version not found in {path.relative_to(ROOT)}")
    return match.group(1)


def release_versions() -> dict[str, str]:
    """Return every independently shipped version marker."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
    return {
        "pyproject.toml": pyproject["project"]["version"],
        "forecost/__init__.py": _match_version(
            ROOT / "forecost/__init__.py", r'^__version__\s*=\s*["\']([^"\']+)["\']'
        ),
        "plugin/.claude-plugin/plugin.json": plugin["version"],
        "plugin/scripts/bootstrap.sh": _match_version(
            ROOT / "plugin/scripts/bootstrap.sh", r'^PLUGIN_VERSION="([^"]+)"'
        ),
    }


def check_release(tag: str | None = None) -> str:
    """Validate release metadata and return the unique package version."""
    versions = release_versions()
    unique = set(versions.values())
    if len(unique) != 1:
        details = ", ".join(f"{name}={version}" for name, version in versions.items())
        raise ValueError(f"release versions disagree: {details}")

    version = unique.pop()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        raise ValueError(f"CHANGELOG.md has no {version} release heading")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"release tag {tag!r} must equal 'v{version}'")
    if tag is not None and re.search(
        rf"^## \[{re.escape(version)}\]\s+-\s+Unreleased\s*$", changelog, re.MULTILINE
    ):
        raise ValueError(f"CHANGELOG.md still marks {version} as Unreleased")
    return version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args()
    version = check_release(args.tag)
    sys.stdout.write(f"release metadata agrees on {version}\n")


if __name__ == "__main__":
    main()
