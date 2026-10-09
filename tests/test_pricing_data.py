"""Pricing overlay: strict validation, fail-safe loading, refresh script gates, opt-in updater."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from forecost import pricing_data
from forecost.cli import main

ROOT = Path(__file__).resolve().parents[1]


def _doc(**models):
    return {
        "schema": 1,
        "generated_at": "2026-10-09",
        "source": "t",
        "models": models or {"m-1": {"input": 1.0, "output": 2.0}},
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema=2),
        lambda d: d.update(generated_at="yesterday"),
        lambda d: d.update(models=[]),
        lambda d: d["models"].update({"bad id!": {"input": 1, "output": 1}}),
        lambda d: d["models"].update({"m-2": {"input": -1, "output": 1}}),
        lambda d: d["models"].update({"m-2": {"input": float("inf"), "output": 1}}),
        lambda d: d["models"].update({"m-2": {"input": 1}}),
        lambda d: d["models"].update({"m-2": {"input": 1, "output": 1, "evil": 1}}),
        lambda d: d["models"].update({"m-2": {"input": True, "output": 1}}),
        lambda d: d["models"].update({"m-2": {"input": 10**9, "output": 1}}),
    ],
)
def test_validate_rejects_malformed_documents(mutate):
    document = _doc()
    mutate(document)
    with pytest.raises(pricing_data.PricingDataError):
        pricing_data.validate(document)


@pytest.mark.parametrize(
    "tiers",
    [
        {"m-1": []},
        {"m-1": [{"input": 1, "output": 1}]},
        {"m-1": [{"above": 0, "input": 1, "output": 1}]},
        {"m-1": [{"above": 5, "input": 1, "output": 1}, {"above": 5, "input": 2, "output": 2}]},
        {"m-1": [{"above": 9, "input": 1, "output": 1}, {"above": 5, "input": 2, "output": 2}]},
        {"m-1": [{"above": 5, "input": 1}]},
        {"bad id": [{"above": 5, "input": 1, "output": 1}]},
        {"m-1": "nope"},
    ],
)
def test_validate_rejects_malformed_tiers(tiers):
    document = _doc()
    document["tiers"] = tiers
    with pytest.raises(pricing_data.PricingDataError):
        pricing_data.validate(document)


def test_validate_accepts_tiers():
    document = _doc()
    document["tiers"] = {"m-1": [{"above": 200000, "input": 2.0, "output": 3.0}]}
    assert pricing_data.validate(document)["tiers"]["m-1"][0]["above"] == 200000


def test_validate_accepts_and_normalizes():
    clean = pricing_data.validate(_doc())
    assert clean["models"] == {"m-1": {"input": 1.0, "output": 2.0}}
    assert clean["tiers"] == {}


def test_read_file_is_fail_safe(tmp_path):
    assert pricing_data.read_file(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert pricing_data.read_file(bad) is None
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (pricing_data.MAX_BYTES + 1))
    assert pricing_data.read_file(big) is None


def test_bundled_data_is_valid_fresh_enough_and_covers_core_models():
    bundled = pricing_data.read_file(pricing_data.BUNDLED_PATH)
    assert bundled is not None
    models = bundled["models"]
    assert len(models) >= 50
    assert "o3" in models
    assert "gemini-2.5-flash" in models


def test_staleness_rules():
    assert pricing_data.is_stale(None)
    assert not pricing_data.is_stale("2026-10-09", today=date(2026, 11, 1))
    assert pricing_data.is_stale("2026-01-01", today=date(2026, 11, 1))


def test_local_override_wins_only_when_not_older(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    bundled = pricing_data.read_file(pricing_data.BUNDLED_PATH)
    assert bundled is not None
    stamp = str(bundled["generated_at"])
    newer = _doc(**{"zz-test-model": {"input": 9.0, "output": 9.0}})
    newer["generated_at"] = "2999-01-01"
    (tmp_path / "pricing.json").write_text(json.dumps(newer))
    rows, effective = pricing_data.load_effective()
    assert "zz-test-model" in rows
    assert effective == "2999-01-01"

    older = _doc(**{"zz-old-model": {"input": 9.0, "output": 9.0}})
    older["generated_at"] = "2000-01-01"
    (tmp_path / "pricing.json").write_text(json.dumps(older))
    rows, effective = pricing_data.load_effective()
    assert "zz-old-model" not in rows
    assert effective == stamp


def _updater():
    spec = importlib.util.spec_from_file_location(
        "update_pricing", ROOT / "scripts/update_pricing.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _feed():
    feed = {
        f"filler-{i}": {
            "mode": "chat",
            "litellm_provider": "openai",
            "input_cost_per_token": 1e-6,
            "output_cost_per_token": 2e-6,
        }
        for i in range(120)
    }
    feed["gemini/gemini-test-flash"] = {
        "mode": "chat",
        "litellm_provider": "gemini",
        "input_cost_per_token": 3e-7,
        "output_cost_per_token": 2.5e-6,
        "cache_read_input_token_cost": 3e-8,
    }
    feed["tiered-model"] = {
        "mode": "chat",
        "litellm_provider": "openai",
        "input_cost_per_token": 1e-6,
        "output_cost_per_token": 2e-6,
        "input_cost_per_token_above_200k_tokens": 2e-6,
        "output_cost_per_token_above_200k_tokens": 3e-6,
    }
    feed["azure-thing"] = {
        "mode": "chat",
        "litellm_provider": "azure",
        "input_cost_per_token": 1e-6,
        "output_cost_per_token": 1e-6,
    }
    feed["some-embedding"] = {
        "mode": "embedding",
        "litellm_provider": "openai",
        "input_cost_per_token": 1e-7,
    }
    return feed


def test_updater_extracts_only_simple_chat_models_in_per_mtok():
    rows = _updater().extract(_feed())
    assert rows["gemini-test-flash"] == {"input": 0.3, "output": 2.5, "cache_read": 0.03}
    assert rows["tiered-model"] == {"input": 1.0, "output": 2.0}
    assert _updater().extract_tiers(_feed()) == {
        "tiered-model": [{"above": 200000, "input": 2.0, "output": 3.0}]
    }
    assert "azure-thing" not in rows
    assert "some-embedding" not in rows


def test_updater_holds_implausible_price_jumps_for_review():
    updater = _updater()
    accepted, held = updater.gate(
        {"a": {"input": 1.0, "output": 1.0}, "b": {"input": 100.0, "output": 1.0}},
        {"a": {"input": 1.2, "output": 1.0}, "b": {"input": 1.0, "output": 1.0}},
    )
    assert "a" in accepted
    assert "b" not in accepted
    assert held
    assert held[0].startswith("b.input")


def test_updater_end_to_end_is_deterministic_and_refuses_junk(tmp_path, monkeypatch):
    updater = _updater()
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps(_feed()))
    out = tmp_path / "pricing.json"
    monkeypatch.setattr(
        "sys.argv", ["u", "--source", str(feed), "--out", str(out), "--today", "2026-10-09"]
    )
    assert updater.main() == 0
    first = out.read_text()
    assert updater.main() == 0
    assert out.read_text() == first
    assert pricing_data.read_file(out) is not None

    junk = tmp_path / "junk.json"
    junk.write_text(json.dumps({"x": 1}))
    monkeypatch.setattr("sys.argv", ["u", "--source", str(junk), "--out", str(out)])
    with pytest.raises(SystemExit):
        updater.main()


def test_pricing_update_command_validates_and_installs(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path / "home"))
    document = _doc(**{"zz-cli-model": {"input": 1.0, "output": 1.0}})
    document["generated_at"] = "2999-01-01"
    source = tmp_path / "src.json"
    source.write_text(json.dumps(document))

    dry = CliRunner().invoke(main, ["pricing-update", "--source", str(source), "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert not (tmp_path / "home" / "pricing.json").exists()

    done = CliRunner().invoke(main, ["pricing-update", "--source", str(source)])
    assert done.exit_code == 0, done.output
    installed = tmp_path / "home" / "pricing.json"
    assert pricing_data.read_file(installed) is not None

    older = _doc()
    older["generated_at"] = "2000-01-01"
    source.write_text(json.dumps(older))
    again = CliRunner().invoke(main, ["pricing-update", "--source", str(source)])
    assert "nothing to do" in again.output


def test_pricing_update_rejects_bad_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("FORECOST_HOME", str(tmp_path))
    plain = CliRunner().invoke(main, ["pricing-update", "--source", "http://example.com/p.json"])
    assert plain.exit_code != 0
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": 1}')
    result = CliRunner().invoke(main, ["pricing-update", "--source", str(bad)])
    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_event_pricing_version_records_data_provenance():
    from forecost.pricing import pricing_data_tag

    assert pricing_data_tag("o3") is not None
    assert pricing_data_tag("totally-unknown-model") is None


def test_refresh_workflow_exists_and_is_scheduled():
    text = (ROOT / ".github/workflows/pricing-refresh.yml").read_text()
    assert "schedule:" in text
    assert "scripts/update_pricing.py" in text
    assert "freshness:" in text


def test_data_provenance_tag_survives_pricing_version_normalization():
    from forecost.adapters.base import _normalize_pricing_version

    readable = "bundled-2026-08/data-2026-10-09/sonnet5-standard-from-2026-09-01"
    assert _normalize_pricing_version(readable) == readable
    hashed = _normalize_pricing_version("bundled-2026-08/data-bogus")
    assert hashed is not None
    assert hashed.startswith("pricing:")
