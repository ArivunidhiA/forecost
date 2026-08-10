#!/usr/bin/env python3
"""Generate offline checksums, an SPDX SBOM, and local build provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        value = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    else:
        value = datetime.now(timezone.utc)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(  # noqa: S603 - fixed executable and fixed caller-owned arguments
        ["/usr/bin/git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _metadata_bytes(path: Path) -> bytes | None:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = sorted(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            return archive.read(names[0]) if len(names) == 1 else None
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = sorted(
                (member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")),
                key=lambda member: member.name,
            )
            extracted = archive.extractfile(members[0]) if len(members) == 1 else None
            return extracted.read() if extracted is not None else None
    return None


def _package_metadata(artifacts: list[Path]) -> tuple[str, str, list[str]]:
    for artifact in artifacts:
        raw = _metadata_bytes(artifact)
        if raw is None:
            continue
        metadata = BytesParser().parsebytes(raw)
        name = metadata.get("Name", "forecost")
        version = metadata.get("Version", "UNKNOWN")
        requirements = sorted(metadata.get_all("Requires-Dist", []))
        return name, version, requirements
    raise ValueError("no artifact contains exactly one Python package metadata record")


def build_evidence(dist: Path, output: Path, source_root: Path) -> dict[str, Path]:
    artifacts = sorted(
        path for path in dist.iterdir() if path.is_file() and not path.is_symlink()
    )
    if not artifacts:
        raise ValueError("distribution directory contains no regular artifacts")
    output.mkdir(parents=True, exist_ok=True)
    created = _timestamp()
    subjects = [
        {"name": path.name, "digest": {"sha256": _sha256(path)}} for path in artifacts
    ]
    name, version, requirements = _package_metadata(artifacts)
    namespace_seed = "|".join(item["digest"]["sha256"] for item in subjects)
    namespace = f"https://forecost.dev/spdx/{hashlib.sha256(namespace_seed.encode()).hexdigest()}"
    sbom = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "name": f"{name}-{version}",
        "documentNamespace": namespace,
        "creationInfo": {"created": created, "creators": ["Tool: forecost-release-evidence/1"]},
        "packages": [
            {
                "SPDXID": "SPDXRef-Package",
                "name": name,
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "MIT",
                "licenseDeclared": "MIT",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": f"pkg:pypi/{name}@{version}",
                    }
                ],
                "annotations": [
                    {"annotationType": "OTHER", "comment": requirement}
                    for requirement in requirements
                ],
            }
        ],
    }
    commit = _git(source_root, "rev-parse", "HEAD") or "UNKNOWN"
    dirty = bool(_git(source_root, "status", "--porcelain"))
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://forecost.dev/build/python-local/v1",
                "externalParameters": {"source_commit": commit},
                "internalParameters": {"dirty_worktree": dirty},
                "resolvedDependencies": [],
            },
            "runDetails": {
                "builder": {"id": "https://forecost.dev/builders/local-offline/v1"},
                "metadata": {
                    "invocationId": namespace,
                    "startedOn": created,
                    "finishedOn": created,
                },
            },
        },
    }
    checksums = {item["name"]: item["digest"]["sha256"] for item in subjects}
    paths = {
        "checksums": output / "checksums.json",
        "sbom": output / "sbom.spdx.json",
        "provenance": output / "provenance.intoto.json",
    }
    documents = {"checksums": checksums, "sbom": sbom, "provenance": provenance}
    for key, path in paths.items():
        path.write_text(
            json.dumps(documents[key], sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("dist/evidence"))
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        paths = build_evidence(args.dist, args.output, args.source_root)
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as error:
        parser.error(str(error))
    for kind, path in sorted(paths.items()):
        sys.stdout.write(f"{kind}: {path}\n")


if __name__ == "__main__":
    main()
