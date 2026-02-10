"""
Budget alert checking and webhook firing for LLMLab.

After each proxy request, check_and_fire_alerts() compares the user's
current monthly spend against their budget thresholds and fires webhooks
when thresholds are newly crossed.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def check_and_fire_alerts(user_id: str, db: Session) -> None:
    """
    Check budget status after a proxy request and fire webhooks if needed.

    This runs as a fire-and-forget asyncio task so it doesn't block the
    proxy response.

    Args:
        user_id: The user whose budgets to check.
        db: Database session.
    """
    from models import Budget, FiredAlert, UsageLog, Webhook

    try:
        # Get user's budgets
        budgets = db.query(Budget).filter(Budget.user_id == user_id).all()
        if not budgets:
            return

        # Get current month's spend
        now = datetime.now(timezone.utc)
        month_start = now - timedelta(days=30)
        current_spend = sum(
            log.cost_usd
            for log in db.query(UsageLog).filter(
                UsageLog.user_id == user_id,
                UsageLog.created_at >= month_start,
            ).all()
        )

        # Get user's active webhooks
        webhooks = db.query(Webhook).filter(
            Webhook.user_id == user_id,
            Webhook.is_active == True,
        ).all()

        if not webhooks:
            return

        for budget in budgets:
            pct = (current_spend / budget.amount_usd * 100) if budget.amount_usd > 0 else 0

            # Determine alert status
            if pct >= 100:
                alert_status = "budget_exceeded"
            elif pct >= budget.alert_threshold:
                alert_status = "budget_warning"
            else:
                continue  # No alert needed

            # Check if we already fired this alert (persisted in DB)
            existing = db.query(FiredAlert).filter(
                FiredAlert.user_id == user_id,
                FiredAlert.budget_id == budget.id,
                FiredAlert.alert_type == alert_status,
            ).first()
            if existing:
                continue

            # Fire matching webhooks
            for webhook in webhooks:
                if webhook.event_type != alert_status:
                    continue

                payload = {
                    "event": alert_status,
                    "budget_id": budget.id,
                    "budget_amount_usd": budget.amount_usd,
                    "current_spend_usd": round(current_spend, 6),
                    "percentage_used": round(pct, 2),
                    "alert_threshold": budget.alert_threshold,
                    "timestamp": now.isoformat(),
                }

                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            webhook.url,
                            json=payload,
                            headers={"Content-Type": "application/json", "User-Agent": "LLMLab/1.0"},
                        )
                        logger.info(
                            f"Webhook fired: {alert_status} to {webhook.url} — status {resp.status_code}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to fire webhook {webhook.url}: {e}")

            # Persist fired alert so we don't spam (survives restarts)
            db.add(FiredAlert(user_id=user_id, budget_id=budget.id, alert_type=alert_status))
            db.commit()

    except Exception as e:
        logger.error(f"Error checking budget alerts for user {user_id}: {e}")


def reset_fired_alerts(db: Session) -> None:
    """Reset the fired alerts tracker (useful for testing or new billing periods)."""
    from models import FiredAlert
    db.query(FiredAlert).delete()
    db.commit()
