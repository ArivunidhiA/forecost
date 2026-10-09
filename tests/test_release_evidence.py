from __future__ import annotations

import json
import zipfile

from scripts.build_release_evidence import build_evidence


def test_release_evidence_is_offline_deterministic_and_hashes_artifact(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "forecost-0.3.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "forecost-0.3.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: forecost\nVersion: 0.3.0\nRequires-Dist: click>=8\n",
        )
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    monkeypatch.setattr("scripts.build_release_evidence._git", lambda *_args: "abc123")

    first = build_evidence(dist, tmp_path / "one", tmp_path)
    second = build_evidence(dist, tmp_path / "two", tmp_path)

    assert first["sbom"].read_bytes() == second["sbom"].read_bytes()
    assert first["provenance"].read_bytes() == second["provenance"].read_bytes()
    checksums = json.loads(first["checksums"].read_text(encoding="utf-8"))
    assert set(checksums) == {wheel.name}
    sbom = json.loads(first["sbom"].read_text(encoding="utf-8"))
    assert sbom["packages"][0]["externalRefs"][0]["referenceLocator"] == ("pkg:pypi/forecost@0.3.0")
