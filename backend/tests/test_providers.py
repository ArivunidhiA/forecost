"""
Tests for provider implementations.

Tests the static-method providers for cost calculation.
"""

import pytest
from providers.openai_provider import OpenAIProvider, OPENAI_PRICING
from providers.anthropic_provider import AnthropicProvider, ANTHROPIC_PRICING
from providers.google_provider import GoogleProvider, GOOGLE_PRICING


class TestOpenAIProvider:
    """Test suite for OpenAI provider."""

    def test_calculate_cost_gpt4o(self):
        """Test GPT-4o cost calculation."""
        # gpt-4o: $2.50/1M input, $10.00/1M output
        cost = OpenAIProvider.calculate_cost("gpt-4o", 1000, 500)
        expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_gpt4o_mini(self):
        """Test GPT-4o-mini cost calculation."""
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        cost = OpenAIProvider.calculate_cost("gpt-4o-mini", 2000, 1000)
        expected = (2000 / 1_000_000) * 0.15 + (1000 / 1_000_000) * 0.60
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_gpt35_turbo(self):
        """Test GPT-3.5-turbo cost calculation."""
        # gpt-3.5-turbo: $0.50/1M input, $1.50/1M output
        cost = OpenAIProvider.calculate_cost("gpt-3.5-turbo", 1000, 500)
        expected = (1000 / 1_000_000) * 0.50 + (500 / 1_000_000) * 1.50
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_unknown_model(self):
        """Test unknown model uses default pricing."""
        cost = OpenAIProvider.calculate_cost("gpt-future-model", 1000, 500)
        assert cost > 0  # Should use default pricing, not zero

    def test_calculate_cost_zero_tokens(self):
        """Test zero tokens returns zero cost."""
        cost = OpenAIProvider.calculate_cost("gpt-4o", 0, 0)
        assert cost == 0.0

    def test_extract_usage(self):
        """Test extracting usage from OpenAI response."""
        response_data = {
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 200,
            }
        }
        input_tokens, output_tokens = OpenAIProvider.extract_usage(response_data)
        assert input_tokens == 150
        assert output_tokens == 200

    def test_extract_usage_empty(self):
        """Test extracting usage from empty response."""
        input_tokens, output_tokens = OpenAIProvider.extract_usage({})
        assert input_tokens == 0
        assert output_tokens == 0

    def test_extract_model(self):
        """Test extracting model from response."""
        response_data = {"model": "gpt-4o-2024-11-20"}
        model = OpenAIProvider.extract_model(response_data, "gpt-4o")
        assert model == "gpt-4o-2024-11-20"

    def test_extract_model_fallback(self):
        """Test model extraction falls back to request model."""
        model = OpenAIProvider.extract_model({}, "gpt-4o")
        assert model == "gpt-4o"

    def test_pricing_dict_has_major_models(self):
        """Verify pricing dict contains key models."""
        assert "gpt-4o" in OPENAI_PRICING
        assert "gpt-4o-mini" in OPENAI_PRICING
        assert "gpt-4" in OPENAI_PRICING
        assert "gpt-3.5-turbo" in OPENAI_PRICING


class TestAnthropicProvider:
    """Test suite for Anthropic provider."""

    def test_calculate_cost_claude35_sonnet(self):
        """Test Claude 3.5 Sonnet cost calculation."""
        # claude-3-5-sonnet: $3.00/1M input, $15.00/1M output
        cost = AnthropicProvider.calculate_cost(
            "claude-3-5-sonnet-20241022", 1000, 500
        )
        expected = (1000 / 1_000_000) * 3.00 + (500 / 1_000_000) * 15.00
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_claude3_haiku(self):
        """Test Claude 3 Haiku cost calculation."""
        # claude-3-haiku: $0.25/1M input, $1.25/1M output
        cost = AnthropicProvider.calculate_cost(
            "claude-3-haiku-20240307", 2000, 1000
        )
        expected = (2000 / 1_000_000) * 0.25 + (1000 / 1_000_000) * 1.25
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_unknown_model(self):
        """Test unknown model uses default pricing."""
        cost = AnthropicProvider.calculate_cost("claude-future", 1000, 500)
        assert cost > 0

    def test_extract_usage(self):
        """Test extracting usage from Anthropic response."""
        response_data = {
            "usage": {
                "input_tokens": 300,
                "output_tokens": 400,
            }
        }
        input_tokens, output_tokens = AnthropicProvider.extract_usage(response_data)
        assert input_tokens == 300
        assert output_tokens == 400

    def test_extract_model(self):
        """Test extracting model from response."""
        response_data = {"model": "claude-3-5-sonnet-20241022"}
        model = AnthropicProvider.extract_model(response_data, "claude-3-5-sonnet-latest")
        assert model == "claude-3-5-sonnet-20241022"

    def test_pricing_dict_has_major_models(self):
        """Verify pricing dict contains key models."""
        assert "claude-3-5-sonnet-20241022" in ANTHROPIC_PRICING
        assert "claude-3-opus-20240229" in ANTHROPIC_PRICING
        assert "claude-3-haiku-20240307" in ANTHROPIC_PRICING


class TestGoogleProvider:
    """Test suite for Google Gemini provider."""

    def test_calculate_cost_gemini15_pro(self):
        """Test Gemini 1.5 Pro cost calculation."""
        # gemini-1.5-pro: $1.25/1M input, $5.00/1M output
        cost = GoogleProvider.calculate_cost("gemini-1.5-pro", 1000, 500)
        expected = (1000 / 1_000_000) * 1.25 + (500 / 1_000_000) * 5.00
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_gemini15_flash(self):
        """Test Gemini 1.5 Flash cost calculation."""
        # gemini-1.5-flash: $0.075/1M input, $0.30/1M output
        cost = GoogleProvider.calculate_cost("gemini-1.5-flash", 2000, 1000)
        expected = (2000 / 1_000_000) * 0.075 + (1000 / 1_000_000) * 0.30
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_gemini20_flash(self):
        """Test Gemini 2.0 Flash cost calculation."""
        # gemini-2.0-flash: $0.10/1M input, $0.40/1M output
        cost = GoogleProvider.calculate_cost("gemini-2.0-flash", 1000, 500)
        expected = (1000 / 1_000_000) * 0.10 + (500 / 1_000_000) * 0.40
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_calculate_cost_unknown_model(self):
        """Test unknown model uses default pricing."""
        cost = GoogleProvider.calculate_cost("gemini-future", 1000, 500)
        assert cost > 0

    def test_extract_usage(self):
        """Test extracting usage from Gemini response."""
        response_data = {
            "usageMetadata": {
                "promptTokenCount": 250,
                "candidatesTokenCount": 350,
            }
        }
        input_tokens, output_tokens = GoogleProvider.extract_usage(response_data)
        assert input_tokens == 250
        assert output_tokens == 350

    def test_extract_usage_empty(self):
        """Test extracting usage from empty response."""
        input_tokens, output_tokens = GoogleProvider.extract_usage({})
        assert input_tokens == 0
        assert output_tokens == 0

    def test_pricing_dict_has_major_models(self):
        """Verify pricing dict contains key models."""
        assert "gemini-1.5-pro" in GOOGLE_PRICING
        assert "gemini-1.5-flash" in GOOGLE_PRICING
        assert "gemini-2.0-flash" in GOOGLE_PRICING
        assert "gemini-pro" in GOOGLE_PRICING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
