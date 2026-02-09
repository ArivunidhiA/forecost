"""
Tests for the budget alert checking and webhook firing logic.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from alerts import check_and_fire_alerts, reset_fired_alerts, _fired_alerts
from models import Budget, UsageLog, Webhook


@pytest.fixture(autouse=True)
def reset_alerts():
    """Reset fired alerts state before each test."""
    reset_fired_alerts()
    yield
    reset_fired_alerts()


class TestCheckAndFireAlerts:
    @pytest.mark.asyncio
    async def test_no_budgets(self, db_session, test_user):
        """Should return without error when user has no budgets."""
        await check_and_fire_alerts(test_user.id, db_session)
        # Should not raise any exceptions

    @pytest.mark.asyncio
    async def test_under_threshold_no_alert(self, db_session, test_user, test_budget, test_webhook):
        """Should not fire webhooks when spend is under threshold."""
        # Add a small usage log (well under the $100 budget * 80% threshold)
        log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            created_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        with patch("alerts.httpx.AsyncClient") as mock_client:
            await check_and_fire_alerts(test_user.id, db_session)
            # httpx should NOT have been called
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_warning_threshold_fires(self, db_session, test_user, test_budget, test_webhook):
        """Should fire budget_warning webhook when threshold is crossed."""
        # Add usage that crosses 80% of $100 = $80
        log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=85.0,
            created_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("alerts.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            await check_and_fire_alerts(test_user.id, db_session)

            # Webhook should have been called
            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args
            assert call_args[1]["json"]["event"] == "budget_warning"
            assert call_args[1]["json"]["current_spend_usd"] == 85.0

    @pytest.mark.asyncio
    async def test_exceeded_threshold_fires(self, db_session, test_user):
        """Should fire budget_exceeded webhook when budget is exceeded."""
        # Create budget and webhook for exceeded
        budget = Budget(
            user_id=test_user.id,
            amount_usd=50.0,
            alert_threshold=80.0,
        )
        webhook = Webhook(
            user_id=test_user.id,
            url="https://example.com/exceeded",
            event_type="budget_exceeded",
        )
        db_session.add(budget)
        db_session.add(webhook)
        db_session.commit()

        # Add usage exceeding $50
        log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=60.0,
            created_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("alerts.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            await check_and_fire_alerts(test_user.id, db_session)

            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args
            assert call_args[1]["json"]["event"] == "budget_exceeded"

    @pytest.mark.asyncio
    async def test_deduplication(self, db_session, test_user, test_budget, test_webhook):
        """Same alert should not fire twice."""
        log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=85.0,
            created_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("alerts.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            # First call fires
            await check_and_fire_alerts(test_user.id, db_session)
            assert mock_instance.post.call_count == 1

            # Second call should NOT fire again
            await check_and_fire_alerts(test_user.id, db_session)
            assert mock_instance.post.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_no_webhooks(self, db_session, test_user, test_budget):
        """Should handle case with budgets but no webhooks."""
        log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=85.0,
            created_at=datetime.utcnow(),
        )
        db_session.add(log)
        db_session.commit()

        # Should not raise
        await check_and_fire_alerts(test_user.id, db_session)

    def test_reset_fired_alerts(self):
        """reset_fired_alerts() should clear the dedup state."""
        _fired_alerts.add(("user1", "budget1", "warning"))
        assert len(_fired_alerts) == 1

        reset_fired_alerts()
        assert len(_fired_alerts) == 0
