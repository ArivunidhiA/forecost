"""
LLMLab API Client - Communication with backend
"""

from typing import Any, Dict, Optional

import requests

from .config import get_api_key, get_backend_url


class APIClient:
    """Client for communicating with LLMLab backend"""

    def __init__(self, api_key: Optional[str] = None, backend_url: Optional[str] = None):
        self.api_key = api_key or get_api_key()
        self.backend_url = backend_url or get_backend_url()
        self.headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def get_status(self, period: str = "month") -> Dict[str, Any]:
        """
        Get current usage stats and budget status.

        Args:
            period: Time period - "today", "week", "month", or "all"

        Returns:
            Status dict with spend and budget info
        """
        response = requests.get(
            f"{self.backend_url}/api/v1/stats",
            params={"period": period},
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def set_budget(self, amount: float, alert_threshold: float = 80.0) -> Dict[str, Any]:
        """
        Create or update monthly budget.

        Args:
            amount: Budget amount in USD
            alert_threshold: Alert threshold percentage (default 80.0)

        Returns:
            Response from backend
        """
        response = requests.post(
            f"{self.backend_url}/api/v1/budgets",
            json={"amount_usd": amount, "alert_threshold": alert_threshold},
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def get_costs(self, period: str = "month") -> Dict[str, Any]:
        """
        Get costs for a time period.

        Args:
            period: Time period - "today", "week", "month", or "all"

        Returns:
            Costs data
        """
        response = requests.get(
            f"{self.backend_url}/api/v1/stats",
            params={"period": period},
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def get_optimization_tips(self) -> Dict[str, Any]:
        """
        Get cost optimization recommendations.

        Returns:
            Optimization tips
        """
        response = requests.get(
            f"{self.backend_url}/api/v1/recommendations",
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
