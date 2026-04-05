"""Tests for forecost.scope module — heuristic project analysis."""

from forecost.scope import analyze_heuristic

EXPECTED_KEYS = {
    "estimated_days",
    "daily_cost",
    "total_cost",
    "confidence",
    "source",
    "project_type",
    "model",
    "calls_per_day",
    "tokens_in",
    "tokens_out",
}


def test_heuristic_detects_openai_project(tmp_path):
    """Directory with 'import openai' should produce an openai-related model."""
    src = tmp_path / "app.py"
    src.write_text("import openai\nclient = openai.OpenAI()\n")
    result = analyze_heuristic(str(tmp_path))
    assert result["source"] == "heuristic"
    assert "gpt" in result["model"] or "openai" in result["model"]
    assert result["daily_cost"] > 0
    assert result["total_cost"] > 0


def test_heuristic_detects_anthropic_project(tmp_path):
    """Directory with 'import anthropic' should select an anthropic model."""
    src = tmp_path / "bot.py"
    src.write_text("import anthropic\nclient = anthropic.Anthropic()\n")
    result = analyze_heuristic(str(tmp_path))
    assert "claude" in result["model"]
    assert result["daily_cost"] > 0


def test_heuristic_empty_directory(tmp_path):
    """Empty directory should return a default result without crashing."""
    result = analyze_heuristic(str(tmp_path))
    assert result["source"] == "heuristic"
    assert result["project_type"] == "default"
    assert result["estimated_days"] > 0


def test_heuristic_no_llm_imports(tmp_path):
    """Python files without SDK imports should produce the default profile."""
    (tmp_path / "main.py").write_text("print('hello world')\n")
    (tmp_path / "utils.py").write_text("import os\nimport sys\n")
    result = analyze_heuristic(str(tmp_path))
    assert result["project_type"] == "default"
    assert result["daily_cost"] > 0


def test_heuristic_nonexistent_path(tmp_path):
    """Non-existent path should return default result without crashing."""
    result = analyze_heuristic(str(tmp_path / "does_not_exist"))
    assert result["source"] == "heuristic"
    assert result["project_type"] == "default"
    assert result["estimated_days"] > 0


def test_heuristic_result_structure(tmp_path):
    """Result dict should contain all expected keys."""
    result = analyze_heuristic(str(tmp_path))
    assert set(result.keys()) == EXPECTED_KEYS


def test_heuristic_costs_are_non_negative(tmp_path):
    """daily_cost and total_cost must never be negative."""
    (tmp_path / "app.py").write_text("import openai\n")
    result = analyze_heuristic(str(tmp_path))
    assert result["daily_cost"] >= 0
    assert result["total_cost"] >= 0

    result_empty = analyze_heuristic(str(tmp_path / "nope"))
    assert result_empty["daily_cost"] >= 0
    assert result_empty["total_cost"] >= 0
