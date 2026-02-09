"""
LLMLab API Client - Communication with backend
"""

import json
from typing import Any, Dict, Optional

import requests

from .config import get_api_key, get_backend_url


class APIClient:
    """Client for communicating with LLMLab backend"""

    def __init__(self, api_key: Optional[str] = None, backend_url: Optional[str] = None):
        self.api_key = api_key or get_api_key()
        self.backend_url = backend_url or get_backend_url()
        self.headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def log_call(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a cost log entry to the backend.

        Args:
            entry: Log entry dict

        Returns:
            Response from backend

        Raises:
            requests.RequestException: If request fails
        """
        response = requests.post(
            f"{self.backend_url}/api/v1/costs/log",
            json=entry,
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def get_status(self) -> Dict[str, Any]:
        """
        Get current month's spend and budget status.

        Returns:
            Status dict with spend and budget info
        """
        response = requests.get(
            f"{self.backend_url}/api/v1/status",
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def set_budget(self, amount: float) -> Dict[str, Any]:
        """
        Set monthly budget.

        Args:
            amount: Budget amount in USD

        Returns:
            Response from backend
        """
        response = requests.post(
            f"{self.backend_url}/api/v1/budget",
            json={"budget": amount},
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()

    def get_costs(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get costs for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Costs data
        """
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        response = requests.get(
            f"{self.backend_url}/api/v1/costs",
            params=params,
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
            f"{self.backend_url}/api/v1/optimize",
            headers=self.headers,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
