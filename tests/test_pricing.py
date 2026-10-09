import pytest

from forecost.pricing import DEFAULT_COST, calculate_cost, get_provider, is_priced


def test_calculate_cost_gpt4o():
    cost = calculate_cost("gpt-4o", 1_000_000, 500_000)
    assert cost == 2.50 + 5.00


def test_calculate_cost_claude():
    cost = calculate_cost("claude-3-5-sonnet-latest", 1_000_000, 500_000)
    assert cost == 3.00 + 7.50


def test_fuzzy_matching_date_suffix():
    cost = calculate_cost("gpt-4o-2024-99-99", 1_000_000, 500_000)
    assert cost == 2.50 + 5.00


def test_unknown_model_falls_back_to_default():
    cost = calculate_cost("unknown-model-xyz", 1_000_000, 500_000)
    expected = (1_000_000 / 1_000_000) * DEFAULT_COST["input"] + (
        500_000 / 1_000_000
    ) * DEFAULT_COST["output"]
    assert cost == expected


def test_get_provider_openai():
    assert get_provider("gpt-4o") == "openai"
    assert get_provider("gpt-4o-mini") == "openai"
    assert get_provider("o1") == "openai"


def test_get_provider_anthropic():
    assert get_provider("claude-3-5-sonnet-latest") == "anthropic"


def test_get_provider_google():
    assert get_provider("gemini-1.5-pro") == "google"
    assert get_provider("text-embedding-004") == "google"


def test_get_provider_mistral():
    assert get_provider("mistral-large-latest") == "mistral"


def test_get_provider_unknown():
    assert get_provider("custom-model") == "unknown"


def test_model_tiers_coverage():
    from forecost.pricing import MODEL_TIERS, get_tier

    all_tiered = []
    for models in MODEL_TIERS.values():
        all_tiered.extend(models)
    assert len(all_tiered) >= 30
    assert get_tier("gpt-4o") == "Tier 1 (Heavy)"
    assert get_tier("gpt-4o-mini") == "Tier 2 (Standard)"
    assert get_tier("gpt-3.5-turbo") == "Tier 3 (Economy)"
    assert get_tier("nonexistent-model") == "Unknown"


def test_get_tier_strips_date_suffix():
    from forecost.pricing import get_tier

    assert get_tier("gpt-4o-2024-08-06") == "Tier 1 (Heavy)"


def test_calculate_cost_ignores_cache_tokens_by_default():
    """Without cache args, cost matches the pre-cache-support calculation exactly."""
    assert calculate_cost("claude-sonnet-4-20250514", 1_000_000, 0) == 3.0


def test_calculate_cost_prices_cache_read_and_write():
    """Cache reads/writes must not be priced at zero (a real bug on agentic workloads
    where cache reads dominate token counts)."""
    base = calculate_cost("claude-sonnet-4-20250514", 0, 0)
    with_cache = calculate_cost(
        "claude-sonnet-4-20250514", 0, 0, cache_read_tokens=1_000_000, cache_write_tokens=1_000_000
    )
    assert with_cache > base
    # explicit rates from FALLBACK_PRICING: cache_read=0.30, cache_write=3.75 per Mtok
    assert with_cache == 0.30 + 3.75


def test_calculate_cost_cache_fallback_ratio_for_models_without_explicit_rates(monkeypatch):
    """A model with no explicit cache_read/cache_write rate falls back to the
    standard 10%/125%-of-input ratio rather than pricing cache tokens at zero."""
    from forecost.pricing import FALLBACK_PRICING

    monkeypatch.setitem(FALLBACK_PRICING, "zz-ratio-model", {"input": 2.5, "output": 10.0})
    cost = calculate_cost(
        "zz-ratio-model", 0, 0, cache_read_tokens=1_000_000, cache_write_tokens=1_000_000
    )
    assert cost == 0.25 + 3.125


def test_calculate_cost_negative_cache_tokens_clamped():
    assert calculate_cost("gpt-4o", 100, 100, cache_read_tokens=-5, cache_write_tokens=-5) >= 0


@pytest.mark.parametrize(
    ("model", "input_rate", "output_rate"),
    [
        ("claude-sonnet-4-5", 3.0, 15.0),
        ("claude-sonnet-4-5-20250929", 3.0, 15.0),
        ("claude-opus-4-5", 5.0, 25.0),
        ("claude-opus-4-1-20250805", 15.0, 75.0),
        ("claude-3-7-sonnet-20250219", 3.0, 15.0),
    ],
)
def test_mainstream_claude_models_are_priced_not_guessed(model, input_rate, output_rate):
    assert is_priced(model)
    assert calculate_cost(model, 100_000, 100_000) == pytest.approx((input_rate + output_rate) / 10)


def test_unknown_future_model_is_not_silently_priced_by_family_prefix():
    assert not is_priced("claude-opus-4-99")


@pytest.mark.parametrize(
    ("model", "input_rate", "output_rate"),
    [
        ("claude-fable-5-1", 10.0, 50.0),
        ("claude-opus-5", 5.0, 25.0),
        ("claude-opus-5-5", 4.0, 20.0),
        ("claude-sonnet-5-5", 2.0, 10.0),
        ("claude-sonnet-5", 2.0, 10.0),
        ("claude-fable-5", 10.0, 50.0),
        ("claude-opus-4-8", 5.0, 25.0),
    ],
)
def test_rates_match_provider_pricing_page_2026_10_09(model, input_rate, output_rate):
    assert calculate_cost(model, 100_000, 100_000) == pytest.approx((input_rate + output_rate) / 10)


@pytest.mark.parametrize(
    ("model", "prompt_tokens", "expected_in", "expected_out"),
    [
        ("claude-haiku-5-5", 100_000, 0.10, 0.50),  # at the boundary: base tier
        ("claude-haiku-5-5", 100_001, 0.50, 2.50),
        ("gemini-2.5-pro", 200_000, 1.25, 10.0),
        ("gemini-2.5-pro", 200_001, 2.50, 15.0),
        ("gpt-5.4", 272_000, 2.50, 15.0),
        ("gpt-5.4", 272_001, 5.00, 22.5),
    ],
)
def test_context_tiered_models_switch_rates_above_the_threshold(
    model, prompt_tokens, expected_in, expected_out
):
    assert is_priced(model)
    cost = calculate_cost(model, prompt_tokens, 1_000_000)
    assert cost == pytest.approx(prompt_tokens / 1e6 * expected_in + expected_out)


def test_tier_threshold_counts_cached_prompt_tokens_too():
    below = calculate_cost("claude-haiku-5-5", 50_000, 0, cache_read_tokens=50_000)
    above = calculate_cost("claude-haiku-5-5", 50_000, 0, cache_read_tokens=50_001)
    assert above > below * 4  # whole request moves to the higher tier


def test_tier_without_cache_rates_derives_them_from_tier_input(monkeypatch):
    from forecost.pricing import FALLBACK_PRICING, TIERED_PRICING

    monkeypatch.setitem(
        FALLBACK_PRICING, "zz-tier", {"input": 1.0, "output": 2.0, "cache_read": 0.5}
    )
    monkeypatch.setitem(TIERED_PRICING, "zz-tier", [{"above": 10, "input": 4.0, "output": 8.0}])
    cost = calculate_cost("zz-tier", 0, 0, cache_read_tokens=1_000_000)
    assert cost == pytest.approx(0.4)  # tier input 4.0 * 10% default ratio, not stale 0.5
