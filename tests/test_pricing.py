from forecost.pricing import DEFAULT_COST, calculate_cost, get_provider


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
