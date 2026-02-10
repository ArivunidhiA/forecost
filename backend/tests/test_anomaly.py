"""Tests for anomaly detection."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from models import UsageLog


class TestDetectAnomalies:
    """Tests for the detect_anomalies() function."""

    def test_no_data_no_anomalies(self, db_session, test_user):
        """No anomalies when there's no data."""
        from anomaly import detect_anomalies

        result = detect_anomalies(test_user.id, db_session)
        assert result == []

    def test_insufficient_data(self, db_session, test_user):
        """No anomalies with insufficient historical data (< 3 days)."""
        from anomaly import detect_anomalies

        now = datetime.utcnow()
        # Only 2 days of data
        for i in range(2):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                created_at=now - timedelta(days=i),
            )
            db_session.add(log)
        db_session.commit()

        result = detect_anomalies(test_user.id, db_session)
        assert result == []

    def test_detect_spend_spike(self, db_session, test_user):
        """Detect a spending spike anomaly."""
        from anomaly import detect_anomalies

        now = datetime.utcnow()
        # 13 normal days at $0.01
        for i in range(1, 14):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                created_at=now - timedelta(days=i),
            )
            db_session.add(log)

        # Today: massive spike
        spike_log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=5.0,  # 500x normal
            created_at=now,
        )
        db_session.add(spike_log)
        db_session.commit()

        result = detect_anomalies(test_user.id, db_session)
        assert len(result) >= 1
        spike_anomaly = [a for a in result if a.type == "spend_spike"]
        assert len(spike_anomaly) >= 1
        assert spike_anomaly[0].severity in ("warning", "critical")

    def test_normal_spending_no_anomaly(self, db_session, test_user):
        """Normal, consistent spending doesn't trigger anomalies."""
        from anomaly import detect_anomalies

        now = datetime.utcnow()
        for i in range(14):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.01,
                created_at=now - timedelta(days=i),
            )
            db_session.add(log)
        db_session.commit()

        result = detect_anomalies(test_user.id, db_session)
        spend_spikes = [a for a in result if a.type == "spend_spike"]
        assert len(spend_spikes) == 0

    def test_detect_token_surge(self, db_session, test_user):
        """Detect a token usage surge."""
        from anomaly import detect_anomalies

        now = datetime.utcnow()
        # 13 normal days with 1500 tokens
        for i in range(1, 14):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=1000,
                output_tokens=500,
                cost_usd=0.01,
                created_at=now - timedelta(days=i),
            )
            db_session.add(log)

        # Today: massive token surge
        surge_log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=0.01,  # cost normal but tokens not
            created_at=now,
        )
        db_session.add(surge_log)
        db_session.commit()

        result = detect_anomalies(test_user.id, db_session)
        token_surges = [a for a in result if a.type == "token_surge"]
        assert len(token_surges) >= 1


class TestAnomalyEndpoint:
    """Tests for GET /api/v1/stats/anomalies."""

    def test_anomalies_endpoint_empty(self, client, auth_headers):
        """Anomalies endpoint returns empty when no data."""
        response = client.get("/api/v1/stats/anomalies", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["anomalies"] == []
        assert data["has_active_anomaly"] is False

    def test_anomalies_endpoint_with_spike(self, client, auth_headers, db_session, test_user):
        """Anomalies endpoint returns events when spike detected."""
        now = datetime.utcnow()
        for i in range(1, 14):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                created_at=now - timedelta(days=i),
            )
            db_session.add(log)

        spike_log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=5.0,
            created_at=now,
        )
        db_session.add(spike_log)
        db_session.commit()

        response = client.get("/api/v1/stats/anomalies", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["has_active_anomaly"] is True
        assert len(data["anomalies"]) >= 1

    def test_requires_auth(self, client):
        """Anomalies endpoint requires authentication."""
        response = client.get("/api/v1/stats/anomalies")
        assert response.status_code == 401


class TestAnomalyWebhookFiring:
    """Tests for check_and_fire_anomaly_alerts()."""

    @pytest.mark.asyncio
    async def test_fire_anomaly_webhook(self, db_session, test_user):
        """Anomaly webhook is fired when spike detected."""
        from anomaly import check_and_fire_anomaly_alerts, reset_fired_anomaly_alerts
        from models import Webhook

        reset_fired_anomaly_alerts()

        now = datetime.utcnow()
        for i in range(1, 14):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                created_at=now - timedelta(days=i),
            )
            db_session.add(log)

        spike_log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=5.0,
            created_at=now,
        )
        db_session.add(spike_log)

        webhook = Webhook(
            user_id=test_user.id,
            url="https://example.com/anomaly-hook",
            event_type="anomaly",
        )
        db_session.add(webhook)
        db_session.commit()

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await check_and_fire_anomaly_alerts(test_user.id, db_session)

            # Webhook should have been called
            assert mock_client.post.call_count >= 1
            call_args = mock_client.post.call_args
            assert "anomaly" in call_args.kwargs.get("json", {}).get("event", "")

    @pytest.mark.asyncio
    async def test_dedup_anomaly_alerts(self, db_session, test_user):
        """Anomaly alerts are not fired twice on the same day."""
        from anomaly import check_and_fire_anomaly_alerts, reset_fired_anomaly_alerts
        from models import Webhook

        reset_fired_anomaly_alerts()

        now = datetime.utcnow()
        for i in range(1, 14):
            log = UsageLog(
                user_id=test_user.id,
                provider="openai",
                model="gpt-4o",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.01,
                created_at=now - timedelta(days=i),
            )
            db_session.add(log)

        spike_log = UsageLog(
            user_id=test_user.id,
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=50000,
            cost_usd=5.0,
            created_at=now,
        )
        db_session.add(spike_log)

        webhook = Webhook(
            user_id=test_user.id,
            url="https://example.com/anomaly-hook",
            event_type="anomaly",
        )
        db_session.add(webhook)
        db_session.commit()

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await check_and_fire_anomaly_alerts(test_user.id, db_session)
            first_count = mock_client.post.call_count

            await check_and_fire_anomaly_alerts(test_user.id, db_session)
            # Count should not increase on second call
            assert mock_client.post.call_count == first_count
