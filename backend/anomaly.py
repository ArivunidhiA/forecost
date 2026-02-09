"""
Anomaly detection for LLMLab.

Detects unusual spending patterns using statistical analysis (Z-score)
and fires webhooks when anomalies are found.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Track fired anomaly alerts to avoid duplicates
_fired_anomaly_alerts: set[tuple[str, str]] = set()


def detect_anomalies(user_id: str, db: Session) -> List:
    """
    Detect spending anomalies for a user.

    Uses Z-score analysis on the last 14 days of daily costs.
    Flags today's spend if it exceeds mean + 2*std.

    Args:
        user_id: The user to check.
        db: Database session.

    Returns:
        List of AnomalyEvent objects.
    """
    from models import UsageLog
    from schemas import AnomalyEvent

    now = datetime.utcnow()
    fourteen_days_ago = now - timedelta(days=14)

    # Get daily costs for last 14 days
    logs = db.query(UsageLog).filter(
        UsageLog.user_id == user_id,
        UsageLog.created_at >= fourteen_days_ago,
    ).all()

    if not logs:
        return []

    # Aggregate by day
    daily_costs: dict[str, float] = {}
    daily_tokens: dict[str, int] = {}
    for log in logs:
        day_key = log.created_at.strftime("%Y-%m-%d")
        daily_costs[day_key] = daily_costs.get(day_key, 0) + log.cost_usd
        daily_tokens[day_key] = daily_tokens.get(day_key, 0) + log.input_tokens + log.output_tokens

    # Fill missing days with 0
    daily_values = []
    for i in range(14):
        day = (fourteen_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_values.append(daily_costs.get(day, 0.0))

    today_key = now.strftime("%Y-%m-%d")
    today_cost = daily_costs.get(today_key, 0.0)
    today_tokens = daily_tokens.get(today_key, 0)

    # Need at least 3 days of historical data
    historical = daily_values[:-1] if len(daily_values) > 1 else daily_values
    if len(historical) < 3:
        return []

    anomalies = []

    # === Spend spike detection ===
    mean_cost = sum(historical) / len(historical)
    variance = sum((x - mean_cost) ** 2 for x in historical) / len(historical)
    std_cost = math.sqrt(variance) if variance > 0 else 0.0

    if std_cost > 0 and today_cost > 0:
        z_score = (today_cost - mean_cost) / std_cost
        if z_score >= 2.0:
            severity = "critical" if z_score >= 3.0 else "warning"
            deviation_factor = round(today_cost / mean_cost, 1) if mean_cost > 0 else 0.0
            anomalies.append(AnomalyEvent(
                type="spend_spike",
                message=f"Spending today (${today_cost:.4f}) is {deviation_factor}x your daily average (${mean_cost:.4f})",
                severity=severity,
                current_value=round(today_cost, 6),
                expected_value=round(mean_cost, 6),
                deviation_factor=round(z_score, 2),
                detected_at=now,
            ))
    elif std_cost == 0 and mean_cost > 0 and today_cost > mean_cost * 2:
        # All historical days had the same cost but today is much higher
        deviation_factor = round(today_cost / mean_cost, 1)
        anomalies.append(AnomalyEvent(
            type="spend_spike",
            message=f"Spending today (${today_cost:.4f}) is {deviation_factor}x your daily average (${mean_cost:.4f})",
            severity="warning",
            current_value=round(today_cost, 6),
            expected_value=round(mean_cost, 6),
            deviation_factor=deviation_factor,
            detected_at=now,
        ))

    # === Token surge detection ===
    token_values = []
    for i in range(14):
        day = (fourteen_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        token_values.append(daily_tokens.get(day, 0))

    hist_tokens = token_values[:-1] if len(token_values) > 1 else token_values
    if hist_tokens:
        mean_tokens = sum(hist_tokens) / len(hist_tokens)
        if mean_tokens > 0 and today_tokens > mean_tokens * 3:
            anomalies.append(AnomalyEvent(
                type="token_surge",
                message=f"Token usage today ({today_tokens:,}) is {today_tokens / mean_tokens:.1f}x your daily average ({mean_tokens:,.0f})",
                severity="info",
                current_value=float(today_tokens),
                expected_value=round(mean_tokens, 0),
                deviation_factor=round(today_tokens / mean_tokens, 2),
                detected_at=now,
            ))

    return anomalies


async def check_and_fire_anomaly_alerts(user_id: str, db: Session) -> None:
    """
    Check for anomalies and fire webhooks if needed.

    This runs as a fire-and-forget asyncio task.
    """
    import httpx
    from models import Webhook

    try:
        anomalies = detect_anomalies(user_id, db)
        if not anomalies:
            return

        # Only fire for warning/critical anomalies
        active_anomalies = [a for a in anomalies if a.severity in ("warning", "critical")]
        if not active_anomalies:
            return

        # Check dedup
        alert_key = (user_id, datetime.utcnow().strftime("%Y-%m-%d"))
        if alert_key in _fired_anomaly_alerts:
            return

        # Get user's anomaly webhooks
        webhooks = db.query(Webhook).filter(
            Webhook.user_id == user_id,
            Webhook.event_type == "anomaly",
            Webhook.is_active == True,
        ).all()

        if not webhooks:
            _fired_anomaly_alerts.add(alert_key)
            return

        for anomaly in active_anomalies:
            payload = {
                "event": "anomaly",
                "type": anomaly.type,
                "message": anomaly.message,
                "severity": anomaly.severity,
                "current_value": anomaly.current_value,
                "expected_value": anomaly.expected_value,
                "deviation_factor": anomaly.deviation_factor,
                "timestamp": anomaly.detected_at.isoformat(),
            }

            for webhook in webhooks:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(
                            webhook.url,
                            json=payload,
                            headers={"Content-Type": "application/json", "User-Agent": "LLMLab/1.0"},
                        )
                except Exception as e:
                    logger.warning(f"Failed to fire anomaly webhook {webhook.url}: {e}")

        _fired_anomaly_alerts.add(alert_key)

    except Exception as e:
        logger.error(f"Error checking anomalies for user {user_id}: {e}")


def reset_fired_anomaly_alerts() -> None:
    """Reset the fired anomaly alerts tracker."""
    _fired_anomaly_alerts.clear()
