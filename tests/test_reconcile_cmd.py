"""Focused output tests for reconcile's pricing-version diagnostics."""

from forecost.commands.reconcile_cmd import _print_multi_version_report


def test_multi_version_report_lists_each_model_and_sorted_versions(capsys):
    _print_multi_version_report(
        {
            "claude-test": {"pricing-2026-02", "pricing-2026-01"},
            "stable-model": {"pricing-2026-01"},
        }
    )

    output = capsys.readouterr().out
    assert "1 model(s) priced under more than one pricing_version" in output
    assert "claude-test: ['pricing-2026-01', 'pricing-2026-02']" in output
    assert "stable-model" not in output
