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
    capabilities = json.loads((ROOT / "docs/capabilities.json").read_text(encoding="utf-8"))
    return {
        "forecost/version.py": _match_version(
            ROOT / "forecost/version.py", r'^__version__\s*=\s*["\']([^"\']+)["\']'
        ),
        "pyproject.toml": pyproject["project"]["version"],
        "plugin/.claude-plugin/plugin.json": plugin["version"],
        "plugin/scripts/bootstrap.sh": _match_version(
            ROOT / "plugin/scripts/bootstrap.sh", r'^PLUGIN_VERSION="([^"]+)"'
        ),
        "docs/capabilities.json": capabilities["package_version"],
        "docs/status.md": _match_version(
            ROOT / "docs/status.md", r"^<!-- package-version: ([^ ]+) -->$"
        ),
    }


def _validate_capabilities(version: str) -> None:
    capabilities = json.loads((ROOT / "docs/capabilities.json").read_text(encoding="utf-8"))
    if capabilities.get("schema_version") != 1:
        raise ValueError("docs/capabilities.json must use capability schema version 1")
    if capabilities.get("package_version") != version:
        raise ValueError("capability package_version disagrees with package version")
    if capabilities.get("product_state") != "experimental-local":
        raise ValueError("capability product_state must remain experimental-local for 0.3.0")

    stores = capabilities.get("stores", {})
    if stores.get("canonical", {}).get("file") != "ledger.db":
        raise ValueError("capability canonical store must be ledger.db")
    if stores.get("legacy", {}).get("file") != "costs.db":
        raise ValueError("capability legacy store must be costs.db")

    cli = capabilities.get("interfaces", {}).get("cli", {})
    if cli.get("legacy_root_aliases") is not False:
        raise ValueError("capabilities may not advertise hidden legacy root aliases")
    mcp = capabilities.get("interfaces", {}).get("mcp", {})
    if mcp.get("tools") != [
        "forecost_list_runs",
        "forecost_get_receipt",
        "forecost_compare_runs",
    ]:
        raise ValueError("MCP capability surface must contain only canonical read tools")
    if "read-only" not in str(mcp.get("store", "")):
        raise ValueError("MCP capability store boundary must be read-only")
    adapters = capabilities.get("adapters", {})
    protocol_names = {
        adapter.get("protocol_name")
        for adapter in adapters.values()
        if adapter.get("protocol_name") is not None
    }
    required_protocols = {
        "claude_jsonl",
        "litellm",
        "otel_genai",
        "openai_agents",
        "langgraph",
    }
    if protocol_names != required_protocols:
        raise ValueError("capability adapter protocol names disagree with the shipped harness")

    status = (ROOT / "docs/status.md").read_text(encoding="utf-8")
    required_status_markers = (
        "<!-- capability-schema-version: 1 -->",
        "<!-- product-contract-version: 1.0 -->",
        "maximum overrun",
        "provider-billed authority",
    )
    for marker in required_status_markers:
        if marker not in status:
            raise ValueError(f"docs/status.md is missing required claim marker: {marker}")


def _validate_public_claims() -> None:
    surfaces = (
        ROOT / "README.md",
        ROOT / "plugin/README.md",
        ROOT / "plugin/.claude-plugin/plugin.json",
    )
    prohibited = (
        "records what your agents actually cost",
        "hard budget enforcement",
        "enforces the same budget",
        "budget enforcement for claude code",
    )
    for path in surfaces:
        content = path.read_text(encoding="utf-8").lower()
        for claim in prohibited:
            if claim in content:
                raise ValueError(
                    f"{path.relative_to(ROOT)} contains unsupported public claim: {claim}"
                )


def _validate_release_authorization() -> None:
    """Refuse an external tag while the machine-readable release hold is active."""
    capabilities = json.loads((ROOT / "docs/capabilities.json").read_text(encoding="utf-8"))
    if capabilities.get("release_hold") is not False:
        raise ValueError(
            "docs/capabilities.json release_hold must be explicitly false before publication"
        )
    blockers = capabilities.get("known_p0_blockers")
    if not isinstance(blockers, list) or blockers:
        raise ValueError("known_p0_blockers must be an explicit empty list before publication")


def check_release(tag: str | None = None) -> str:
    """Validate release metadata and return the unique package version."""
    versions = release_versions()
    unique = set(versions.values())
    if len(unique) != 1:
        details = ", ".join(f"{name}={version}" for name, version in versions.items())
        raise ValueError(f"release versions disagree: {details}")

    version = unique.pop()
    _validate_capabilities(version)
    _validate_public_claims()
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        raise ValueError(f"CHANGELOG.md has no {version} release heading")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"release tag {tag!r} must equal 'v{version}'")
    if tag is not None and re.search(
        rf"^## \[{re.escape(version)}\]\s+-\s+Unreleased\s*$", changelog, re.MULTILINE
    ):
        raise ValueError(f"CHANGELOG.md still marks {version} as Unreleased")
    if tag is not None:
        _validate_release_authorization()
    return version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args()
    version = check_release(args.tag)
    sys.stdout.write(f"release metadata agrees on {version}\n")


if __name__ == "__main__":
    main()
