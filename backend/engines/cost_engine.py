"""
Cost calculation engine.

Provides cost calculation, budget checking, and aggregation functions
using the static-method providers.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from providers.openai_provider import OpenAIProvider
from providers.anthropic_provider import AnthropicProvider
from providers.google_provider import GoogleProvider

logger = logging.getLogger(__name__)

# Provider dispatch map
PROVIDER_CALCULATORS = {
    "openai": OpenAIProvider.calculate_cost,
    "anthropic": AnthropicProvider.calculate_cost,
    "google": GoogleProvider.calculate_cost,
}


class CostCalculationEngine:
    """Engine for calculating and aggregating costs."""

    def calculate_call_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Calculate cost for a single API call.

        Args:
            provider: Provider name (openai, anthropic, google)
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        calculator = PROVIDER_CALCULATORS.get(provider.lower())
        if not calculator:
            logger.warning(f"Unknown provider: {provider}")
            return 0.0

        return calculator(model, input_tokens, output_tokens)

    def check_budget(self, current_spend: float, budget_limit: float) -> Tuple[str, float]:
        """
        Check if within budget and return status.

        Args:
            current_spend: Current spending amount
            budget_limit: Budget limit

        Returns:
            Tuple of (status, percentage_used)
        """
        if budget_limit == 0:
            return "ok", 0.0

        percentage = (current_spend / budget_limit) * 100

        if percentage >= 100:
            return "exceeded", percentage
        elif percentage >= 80:
            return "warning", percentage
        else:
            return "ok", percentage

    def aggregate_by_model(self, events: List[Dict]) -> List[Dict]:
        """
        Aggregate costs by model.

        Args:
            events: List of event dictionaries

        Returns:
            List of dicts with model, provider, total_calls, total_tokens, total_cost
        """
        model_costs: Dict[Tuple[str, str], Dict] = {}

        for event in events:
            key = (event["model"], event["provider"])

            if key not in model_costs:
                model_costs[key] = {
                    "model": event["model"],
                    "provider": event["provider"],
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                }

            model_costs[key]["total_calls"] += 1
            model_costs[key]["total_tokens"] += event.get("input_tokens", 0) + event.get("output_tokens", 0)
            model_costs[key]["total_cost"] += event.get("cost", 0)

        return list(model_costs.values())

    def aggregate_by_date(self, events: List[Dict]) -> List[Dict]:
        """
        Aggregate costs by date.

        Args:
            events: List of event dictionaries

        Returns:
            List of dicts with date, total_cost, call_count
        """
        date_costs: Dict[str, Dict] = {}

        for event in events:
            timestamp = event.get("timestamp")
            if isinstance(timestamp, datetime):
                date_str = timestamp.strftime("%Y-%m-%d")
            else:
                date_str = str(timestamp).split("T")[0]

            if date_str not in date_costs:
                date_costs[date_str] = {
                    "date": date_str,
                    "total_cost": 0.0,
                    "call_count": 0,
                }

            date_costs[date_str]["total_cost"] += event.get("cost", 0)
            date_costs[date_str]["call_count"] += 1

        sorted_dates = sorted(date_costs.items())
        return [data for _, data in sorted_dates]

    def generate_summary(
        self,
        events: List[Dict],
        date_range_start: Optional[str] = None,
        date_range_end: Optional[str] = None,
    ) -> Dict:
        """
        Generate cost summary.

        Args:
            events: List of event dictionaries
            date_range_start: Start date (YYYY-MM-DD)
            date_range_end: End date (YYYY-MM-DD)

        Returns:
            Summary dict with total_cost, call_count, by_model, by_date
        """
        if not events:
            return {
                "total_cost": 0.0,
                "call_count": 0,
                "average_cost_per_call": 0.0,
                "by_model": [],
                "by_date": [],
            }

        total_cost = sum(event.get("cost", 0) for event in events)
        call_count = len(events)
        avg_cost = total_cost / call_count if call_count > 0 else 0.0

        return {
            "total_cost": round(total_cost, 6),
            "call_count": call_count,
            "average_cost_per_call": round(avg_cost, 6),
            "by_model": self.aggregate_by_model(events),
            "by_date": self.aggregate_by_date(events),
        }
