"""
Recommendations engine for cost optimization.

Analyzes usage patterns and generates actionable recommendations
for reducing LLM API costs.
"""

from typing import Dict, List
from datetime import datetime
import statistics
import logging

from providers.openai_provider import OpenAIProvider, OPENAI_PRICING
from providers.anthropic_provider import AnthropicProvider, ANTHROPIC_PRICING
from providers.google_provider import GoogleProvider, GOOGLE_PRICING

logger = logging.getLogger(__name__)


class RecommendationsEngine:
    """Engine for generating cost optimization recommendations."""

    def detect_anomalies(
        self,
        events: List[Dict],
        threshold_std_dev: float = 2.0,
    ) -> List[Dict]:
        """
        Detect spending anomalies using z-score.

        Args:
            events: List of event dictionaries with costs
            threshold_std_dev: Z-score threshold for anomaly detection

        Returns:
            List of anomaly dicts
        """
        if len(events) < 3:
            return []

        costs = [event.get("cost", 0) for event in events]

        try:
            mean_cost = statistics.mean(costs)
            std_dev = statistics.stdev(costs)

            if std_dev == 0:
                return []

            anomalies = []
            for event in events:
                cost = event.get("cost", 0)
                z_score = abs((cost - mean_cost) / std_dev)

                if z_score > threshold_std_dev:
                    anomalies.append({
                        "model": event.get("model"),
                        "cost": cost,
                        "z_score": round(z_score, 2),
                        "severity": "high" if z_score > 3 else "medium",
                    })

            return anomalies
        except (ValueError, statistics.StatisticsError):
            return []

    def get_model_switch_recommendations(
        self,
        events: List[Dict],
    ) -> List[Dict]:
        """
        Generate model switching recommendations.

        Args:
            events: List of event dictionaries

        Returns:
            List of recommendation dicts
        """
        recommendations = []

        # Group by model and calculate costs
        model_stats: Dict[str, Dict] = {}
        for event in events:
            model = event.get("model")
            provider = event.get("provider")
            cost = event.get("cost", 0)

            if model not in model_stats:
                model_stats[model] = {
                    "provider": provider,
                    "total_cost": 0.0,
                    "calls": 0,
                }

            model_stats[model]["total_cost"] += cost
            model_stats[model]["calls"] += 1

        # Model switch suggestions
        expensive_models = {
            "gpt-4": {"alternative": "gpt-4o", "provider": "openai"},
            "gpt-4-turbo": {"alternative": "gpt-4o", "provider": "openai"},
            "gpt-4o": {"alternative": "gpt-4o-mini", "provider": "openai"},
            "claude-3-opus-20240229": {"alternative": "claude-3-5-sonnet-20241022", "provider": "anthropic"},
            "claude-3-opus-latest": {"alternative": "claude-3-5-sonnet-latest", "provider": "anthropic"},
        }

        for model, stats in model_stats.items():
            if model in expensive_models:
                alt = expensive_models[model]
                alt_model = alt["alternative"]

                # Calculate savings estimate
                current_pricing = OPENAI_PRICING.get(model) or ANTHROPIC_PRICING.get(model)
                alt_pricing = OPENAI_PRICING.get(alt_model) or ANTHROPIC_PRICING.get(alt_model)

                if current_pricing and alt_pricing:
                    # Assume 500 input + 500 output tokens average
                    current_cost_per_call = (500 / 1_000_000) * (current_pricing["input"] + current_pricing["output"])
                    alt_cost_per_call = (500 / 1_000_000) * (alt_pricing["input"] + alt_pricing["output"])
                    monthly_savings = (current_cost_per_call - alt_cost_per_call) * stats["calls"]

                    if monthly_savings > 0:
                        recommendations.append({
                            "type": "model_switch",
                            "title": f"Switch from {model} to {alt_model}",
                            "description": f"Based on {stats['calls']} calls, switching to {alt_model} could save ~${monthly_savings:.2f}/month with comparable quality.",
                            "potential_savings": round(monthly_savings, 2),
                            "priority": "high" if monthly_savings > 10 else "medium",
                            "current_model": model,
                            "suggested_model": alt_model,
                        })

        return recommendations

    def get_general_optimizations(self, events: List[Dict]) -> List[Dict]:
        """
        Generate general cost optimization recommendations.

        Args:
            events: List of event dictionaries

        Returns:
            List of optimization dicts
        """
        optimizations = []
        if not events:
            return optimizations

        call_count = len(events)
        total_tokens = sum(
            event.get("input_tokens", 0) + event.get("output_tokens", 0)
            for event in events
        )

        if call_count > 10:
            optimizations.append({
                "type": "caching",
                "title": "Implement Response Caching",
                "description": "Cache API responses for repeated queries to avoid redundant API calls.",
                "potential_savings": round(call_count * 0.002, 2),
                "priority": "high",
            })

        if total_tokens > 100000:
            optimizations.append({
                "type": "token_optimization",
                "title": "Optimize Token Usage",
                "description": "Reduce token consumption by trimming unnecessary context and using shorter prompts.",
                "potential_savings": round(total_tokens * 0.000001, 2),
                "priority": "medium",
            })

        if call_count > 50:
            optimizations.append({
                "type": "batch_processing",
                "title": "Implement Batch Processing",
                "description": "Group multiple requests together to reduce API overhead.",
                "potential_savings": round(call_count * 0.001, 2),
                "priority": "medium",
            })

        return optimizations

    def generate_recommendations(self, events: List[Dict]) -> Dict:
        """
        Generate all recommendations.

        Args:
            events: List of event dictionaries

        Returns:
            Dict with recommendations list and total_potential_savings
        """
        model_recs = self.get_model_switch_recommendations(events)
        general_recs = self.get_general_optimizations(events)

        all_recs = model_recs + general_recs
        total_savings = sum(r.get("potential_savings", 0) for r in all_recs)

        return {
            "recommendations": all_recs,
            "total_potential_savings": round(total_savings, 2),
            "analyzed_period_days": 30,
        }
