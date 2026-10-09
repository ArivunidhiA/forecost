"""CLI contract tests for strict matched comparison and diagnostic abstention."""

from __future__ import annotations

import json
import sqlite3

from click.testing import CliRunner

from forecost.commands.compare_cmd import _MAX_MANIFEST_BYTES, compare
from forecost.lab import seed_demo


def test_two_run_comparison_is_descriptive_and_abstains(ledger_conn, monkeypatch) -> None:
    monkeypatch.setattr("forecost.commands.compare_cmd.get_readonly_ledger_db", lambda: ledger_conn)
    baseline = seed_demo(ledger_conn, seed=101)
    candidate = seed_demo(ledger_conn, seed=103)

    result = CliRunner().invoke(compare, [baseline, candidate, "--json-output"])

    assert result.exit_code == 3
    payload = json.loads(result.output)
    assert payload["schema"] == "forecost.compare/1"
    assert payload["decision"]["status"] == "abstain"
    assert "COMPARISON_MANIFEST_REQUIRED" in payload["decision"]["reason_codes"]
    assert payload["scope"] == {
        "authority": "list_rate",
        "claim_mode": "observational",
        "currency": "USD",
        "line_items": ["model_inference"],
    }
    assert payload["economics"]["baseline_total_micros"] == 125_000
    assert payload["economics"]["candidate_total_micros"] == 125_000


def test_diagnostic_markdown_projects_abstention(ledger_conn, monkeypatch) -> None:
    monkeypatch.setattr("forecost.commands.compare_cmd.get_readonly_ledger_db", lambda: ledger_conn)
    baseline = seed_demo(ledger_conn, seed=107)
    candidate = seed_demo(ledger_conn, seed=109)

    result = CliRunner().invoke(compare, [baseline, candidate, "--markdown"])

    assert result.exit_code == 3
    assert result.output.startswith("# Forecost comparison")
    assert "abstain" in result.output.lower()
    assert "COMPARISON_MANIFEST_REQUIRED" in result.output
    assert "saved" not in result.output.lower()


def test_compare_parser_and_configuration_errors_use_exit_64(tmp_path) -> None:
    runner = CliRunner()
    missing = runner.invoke(compare, [])
    mixed_output = runner.invoke(compare, ["a", "b", "--json-output", "--markdown"])

    policy = tmp_path / "policy.json"
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    for path in (policy, baseline, candidate):
        path.write_text("{}", encoding="utf-8")
    invalid_policy = runner.invoke(
        compare,
        [str(baseline), str(candidate), "--policy", str(policy), "--json-output"],
    )

    assert missing.exit_code == 64
    assert mixed_output.exit_code == 64
    assert invalid_policy.exit_code == 64
    assert "configuration error" in invalid_policy.output


def test_compare_rejects_duplicate_json_keys(tmp_path) -> None:
    policy = tmp_path / "policy.json"
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    policy.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    baseline.write_text("{}", encoding="utf-8")
    candidate.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        compare,
        [str(baseline), str(candidate), "--policy", str(policy)],
    )

    assert result.exit_code == 64
    assert "duplicate JSON key" in result.output


def test_schema_invalid_manifest_is_rejected_before_the_ledger_opens(tmp_path, monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("ledger should not be opened for invalid JSON")

    monkeypatch.setattr("forecost.commands.compare_cmd.get_readonly_ledger_db", fail_if_called)
    policy = tmp_path / "policy.json"
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    policy.write_text("{}", encoding="utf-8")
    baseline.write_text("{}", encoding="utf-8")
    candidate.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        compare,
        [str(baseline), str(candidate), "--policy", str(policy)],
    )

    assert result.exit_code == 64
    assert "configuration error" in result.output
    assert not isinstance(result.exception, AssertionError)


def test_manifest_reader_enforces_actual_byte_limit(tmp_path, monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("ledger should not be opened for oversized input")

    monkeypatch.setattr("forecost.commands.compare_cmd.get_readonly_ledger_db", fail_if_called)
    policy = tmp_path / "policy.json"
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    policy.write_text("{}", encoding="utf-8")
    candidate.write_text("{}", encoding="utf-8")
    baseline.write_bytes(b" " * (_MAX_MANIFEST_BYTES + 1))

    result = CliRunner().invoke(
        compare,
        [str(baseline), str(candidate), "--policy", str(policy)],
    )

    assert result.exit_code == 64
    assert "exceeds 8 MiB" in result.output
    assert not isinstance(result.exception, AssertionError)


def test_manifest_mode_wires_loaded_objects_and_pass_exit(tmp_path, monkeypatch) -> None:
    seen: dict[str, object] = {}

    def compare_stub(conn, baseline, candidate, policy):
        seen.update(conn=conn, baseline=baseline, candidate=candidate, policy=policy)
        return {
            "schema": "forecost.compare/1",
            "decision": {"status": "pass", "reason_codes": []},
        }

    sentinel = sqlite3.connect(":memory:")
    monkeypatch.setattr("forecost.commands.compare_cmd.get_readonly_ledger_db", lambda: sentinel)
    monkeypatch.setattr("forecost.commands.compare_cmd.compare_manifests", compare_stub)
    monkeypatch.setattr(
        "forecost.commands.compare_cmd.validate_comparison_inputs",
        lambda *_args: None,
    )
    policy = tmp_path / "policy.json"
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    policy.write_text('{"kind":"policy"}', encoding="utf-8")
    baseline.write_text('{"arm":"baseline"}', encoding="utf-8")
    candidate.write_text('{"arm":"candidate"}', encoding="utf-8")

    result = CliRunner().invoke(
        compare,
        [str(baseline), str(candidate), "--policy", str(policy), "--json-output"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["decision"]["status"] == "pass"
    assert seen == {
        "conn": sentinel,
        "baseline": {"arm": "baseline"},
        "candidate": {"arm": "candidate"},
        "policy": {"kind": "policy"},
    }


def test_diagnostic_identifiers_are_validated_before_the_ledger_opens(monkeypatch) -> None:
    def fail_if_called():
        raise AssertionError("ledger should not be opened for invalid identifiers")

    monkeypatch.setattr("forecost.commands.compare_cmd.get_readonly_ledger_db", fail_if_called)

    result = CliRunner().invoke(compare, ["contains a space", "candidate"])

    assert result.exit_code == 64
    assert "configuration error" in result.output
    assert not isinstance(result.exception, AssertionError)


def test_compare_internal_failure_is_bounded_exit_5(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("raw internal detail")

    monkeypatch.setattr("forecost.commands.compare_cmd.compare_runs_diagnostic", fail)

    result = CliRunner().invoke(compare, ["baseline", "candidate"])

    assert result.exit_code == 5
    assert "no decision was produced" in result.output
    assert "raw internal detail" not in result.output
