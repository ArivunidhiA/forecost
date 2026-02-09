"""
Tests for cost calculation engine.

Tests the CostCalculationEngine class with the new static-method providers.
"""

import pytest
from datetime import datetime, timedelta
from engines import CostCalculationEngine


class TestCostCalculationEngine:
    """Test suite for CostCalculationEngine."""

    @pytest.fixture
    def engine(self):
        """Create cost engine instance."""
        return CostCalculationEngine()

    def test_openai_cost_calculation(self, engine):
        """Test OpenAI model cost calculation through engine."""
        cost = engine.calculate_call_cost(
            provider="openai",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )
        # gpt-4o: $2.50/1M input, $10.00/1M output
        expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_anthropic_cost_calculation(self, engine):
        """Test Anthropic model cost calculation through engine."""
        cost = engine.calculate_call_cost(
            provider="anthropic",
            model="claude-3-haiku-20240307",
            input_tokens=1000,
            output_tokens=500,
        )
        # claude-3-haiku: $0.25/1M input, $1.25/1M output
        expected = (1000 / 1_000_000) * 0.25 + (500 / 1_000_000) * 1.25
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_google_cost_calculation(self, engine):
        """Test Google model cost calculation through engine."""
        cost = engine.calculate_call_cost(
            provider="google",
            model="gemini-1.5-pro",
            input_tokens=500,
            output_tokens=300,
        )
        # gemini-1.5-pro: $1.25/1M input, $5.00/1M output
        expected = (500 / 1_000_000) * 1.25 + (300 / 1_000_000) * 5.00
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_invalid_provider(self, engine):
        """Test handling of invalid provider."""
        cost = engine.calculate_call_cost(
            provider="invalid",
            model="test-model",
            input_tokens=100,
            output_tokens=50,
        )
        assert cost == 0.0

    def test_budget_check_under_limit(self, engine):
        """Test budget check when under limit."""
        status, percentage = engine.check_budget(50.0, 100.0)
        assert status == "ok"
        assert percentage == 50.0

    def test_budget_check_warning(self, engine):
        """Test budget check when approaching limit."""
        status, percentage = engine.check_budget(85.0, 100.0)
        assert status == "warning"
        assert percentage == 85.0

    def test_budget_check_exceeded(self, engine):
        """Test budget check when exceeded."""
        status, percentage = engine.check_budget(150.0, 100.0)
        assert status == "exceeded"
        assert percentage == 150.0

    def test_budget_check_zero_limit(self, engine):
        """Test budget check with zero limit."""
        status, percentage = engine.check_budget(50.0, 0)
        assert status == "ok"
        assert percentage == 0.0

    def test_aggregate_by_model(self, engine):
        """Test aggregating costs by model."""
        events = [
            {
                "model": "gpt-4",
                "provider": "openai",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": 0.005,
            },
            {
                "model": "gpt-4",
                "provider": "openai",
                "input_tokens": 200,
                "output_tokens": 100,
                "cost": 0.010,
            },
            {
                "model": "claude-3-opus",
                "provider": "anthropic",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": 0.002,
            },
        ]

        result = engine.aggregate_by_model(events)

        assert len(result) == 2

        gpt4_result = [r for r in result if r["model"] == "gpt-4"][0]
        assert gpt4_result["total_calls"] == 2
        assert gpt4_result["total_cost"] == pytest.approx(0.015, rel=1e-6)
        assert gpt4_result["total_tokens"] == 450

    def test_aggregate_by_date(self, engine):
        """Test aggregating costs by date."""
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        events = [
            {"timestamp": now, "cost": 0.005},
            {"timestamp": now, "cost": 0.010},
            {"timestamp": yesterday, "cost": 0.002},
        ]

        result = engine.aggregate_by_date(events)

        assert len(result) == 2

        # First date should be yesterday (sorted)
        assert result[0]["call_count"] == 1
        assert result[0]["total_cost"] == pytest.approx(0.002, rel=1e-6)

    def test_generate_summary(self, engine):
        """Test generating cost summary."""
        now = datetime.now()

        events = [
            {
                "model": "gpt-4",
                "provider": "openai",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost": 0.005,
                "timestamp": now,
            },
            {
                "model": "gpt-3.5-turbo",
                "provider": "openai",
                "input_tokens": 1000,
                "output_tokens": 500,
                "cost": 0.001,
                "timestamp": now,
            },
        ]

        summary = engine.generate_summary(events)

        assert summary["total_cost"] == pytest.approx(0.006, rel=1e-6)
        assert summary["call_count"] == 2
        assert summary["average_cost_per_call"] == pytest.approx(0.003, rel=1e-6)
        assert len(summary["by_model"]) == 2
        assert len(summary["by_date"]) == 1

    def test_generate_summary_empty(self, engine):
        """Test generating summary with no events."""
        summary = engine.generate_summary([])

        assert summary["total_cost"] == 0.0
        assert summary["call_count"] == 0
        assert summary["average_cost_per_call"] == 0.0
        assert len(summary["by_model"]) == 0
        assert len(summary["by_date"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
