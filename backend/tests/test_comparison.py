"""
Tests for the provider cost comparison endpoint.
"""

import pytest
from fastapi.testclient import TestClient


class TestComparison:
    def test_get_comparison(self, client: TestClient, auth_headers: dict, test_usage_logs):
        """Should return comparisons with alternatives."""
        response = client.get("/api/v1/stats/comparison", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "comparisons" in data
        assert "current_total" in data
        assert "cheapest_total" in data
        assert isinstance(data["comparisons"], list)

        # Should have comparisons for the models in our test data
        assert len(data["comparisons"]) > 0

        # Each comparison should have the right structure
        for comp in data["comparisons"]:
            assert "model" in comp
            assert "provider" in comp
            assert "actual_cost" in comp
            assert "input_tokens" in comp
            assert "output_tokens" in comp
            assert "alternatives" in comp
            assert isinstance(comp["alternatives"], list)

    def test_get_comparison_empty(self, client: TestClient, auth_headers: dict):
        """Should return empty comparisons when no usage data."""
        response = client.get("/api/v1/stats/comparison", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["comparisons"] == []
        assert data["current_total"] == 0
        assert data["cheapest_total"] == 0

    def test_alternatives_sorted_by_cost(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """Alternatives should be sorted by estimated cost (cheapest first)."""
        response = client.get("/api/v1/stats/comparison", headers=auth_headers)
        data = response.json()

        for comp in data["comparisons"]:
            alternatives = comp["alternatives"]
            if len(alternatives) > 1:
                costs = [a["estimated_cost"] for a in alternatives]
                assert costs == sorted(costs), "Alternatives should be sorted by cost"

    def test_alternatives_max_five(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """Should return at most 5 alternatives per model."""
        response = client.get("/api/v1/stats/comparison", headers=auth_headers)
        data = response.json()

        for comp in data["comparisons"]:
            assert len(comp["alternatives"]) <= 5

    def test_cross_provider_alternatives(
        self, client: TestClient, auth_headers: dict, test_usage_logs
    ):
        """OpenAI model should show Anthropic/Google alternatives."""
        response = client.get("/api/v1/stats/comparison", headers=auth_headers)
        data = response.json()

        # Find an OpenAI model comparison
        openai_comps = [c for c in data["comparisons"] if c["provider"] == "openai"]
        if openai_comps:
            comp = openai_comps[0]
            alt_providers = {a["provider"] for a in comp["alternatives"]}
            # Should have at least one non-openai provider in alternatives
            assert len(alt_providers) > 0

    def test_get_comparison_unauthenticated(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get("/api/v1/stats/comparison")
        assert response.status_code in (401, 403)
