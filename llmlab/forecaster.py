"""
Adaptive Exponential Smoothing forecasting engine for LLM cost tracking.
"""

from __future__ import annotations

from llmlab.db import get_daily_costs, get_forecast_history, get_or_create_db, save_forecast


class ProjectForecaster:
    def __init__(self, project_id: int) -> None:
        conn = get_or_create_db()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise ValueError(f"Project {project_id} not found")
        self._project = dict(row)
        self._project_id = project_id
        self._project_name = self._project["name"]
        self._baseline_daily_cost = float(self._project["baseline_daily_cost"])
        self._baseline_total_days = int(self._project["baseline_total_days"])
        self._baseline_total_cost = float(self._project["baseline_total_cost"])
        self._daily_costs = get_daily_costs(project_id)
        self._forecast_history = get_forecast_history(project_id)

    def calculate_forecast(self, *, save: bool = False) -> dict:
        active_days_data = [(day, cost) for day, cost in self._daily_costs if cost > 0]
        n = len(active_days_data)
        daily_costs = [c for _, c in active_days_data]

        baseline_daily = self._baseline_daily_cost if self._baseline_daily_cost > 0 else 1.0
        daily_burn_ratios = [c / baseline_daily for c in daily_costs]

        alpha = min(0.6, 0.15 + 0.03 * n)
        smoothed_ratio = 1.0
        for ratio in daily_burn_ratios:
            smoothed_ratio = alpha * ratio + (1 - alpha) * smoothed_ratio

        actual_spend = sum(daily_costs)
        remaining_active_days = max(1, self._baseline_total_days - n)
        projected_remaining = smoothed_ratio * self._baseline_daily_cost * remaining_active_days
        projected_total = actual_spend + projected_remaining

        conn = get_or_create_db()
        model_rows = conn.execute(
            "SELECT model, SUM(cost_usd) AS cost FROM usage_logs "
            "WHERE project_id = ? GROUP BY model",
            (self._project_id,),
        ).fetchall()
        total_cost = actual_spend
        model_breakdown = []
        if total_cost > 0:
            for r in model_rows:
                spent = float(r["cost"])
                share = spent / total_cost
                projected = spent + share * projected_remaining
                model_breakdown.append(
                    {"model": r["model"], "spent": spent, "projected": projected, "share": share}
                )

        last_n = min(len(daily_burn_ratios), 5)
        last_ratios = daily_burn_ratios[-last_n:] if daily_burn_ratios else []
        consecutive_over = 0
        for r in reversed(last_ratios):
            if r > 1.5:
                consecutive_over += 1
            else:
                break
        consecutive_under = 0
        for r in reversed(last_ratios):
            if r < 0.5:
                consecutive_under += 1
            else:
                break
        if smoothed_ratio > 1.5 and consecutive_over >= 3:
            drift_status = "over_budget"
        elif smoothed_ratio < 0.5 and consecutive_under >= 3:
            drift_status = "under_budget"
        else:
            drift_status = "on_track"

        if n == 0:
            confidence = "low"
        elif n <= 3:
            confidence = "medium-low"
        elif n <= 7:
            confidence = "medium"
        elif n <= 14:
            confidence = "high"
        else:
            confidence = "very-high"

        # Forecast stability: how much the projection changes between runs.
        # Unlike MAPE (which needs ground truth), this measures convergence.
        stability = None
        stability_label = None
        history_totals = [h["projected_total"] for h in self._forecast_history]
        history_totals.append(projected_total)
        recent = history_totals[-5:]
        if len(recent) >= 2:
            changes = [
                abs(recent[i] - recent[i - 1]) / recent[i] * 100
                for i in range(1, len(recent))
                if recent[i] > 0
            ]
            if changes:
                stability = sum(changes) / len(changes)
                if stability < 5:
                    stability_label = "converged"
                elif stability <= 15:
                    stability_label = "stabilizing"
                else:
                    stability_label = "adjusting"

        iteration = len(self._forecast_history) + 1

        if save:
            save_forecast(
                self._project_id,
                iteration,
                projected_total,
                remaining_active_days,
                smoothed_ratio,
                confidence,
                n,
                stability,
            )

        return {
            "project_id": self._project_id,
            "project_name": self._project_name,
            "actual_spend": actual_spend,
            "projected_total": projected_total,
            "projected_remaining": projected_remaining,
            "remaining_days": remaining_active_days,
            "active_days": n,
            "total_days": self._baseline_total_days,
            "smoothed_burn_ratio": smoothed_ratio,
            "drift_status": drift_status,
            "confidence": confidence,
            "stability": stability,
            "stability_label": stability_label,
            "model_breakdown": model_breakdown,
            "iteration": iteration,
            "baseline_daily_cost": self._baseline_daily_cost,
            "baseline_total_cost": self._baseline_total_cost,
        }
