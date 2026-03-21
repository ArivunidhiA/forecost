"""
Ensemble forecasting engine for LLM cost tracking.

Uses a three-model combination (SES + Damped Trend + Linear Regression)
inspired by the M4 Forecasting Competition, where simple combinations
beat all pure ML methods for short time series.

Falls back to hand-rolled EMA when statsmodels is not installed.
"""

from __future__ import annotations

import math
import warnings

from llmcast.db import get_daily_costs, get_forecast_history, get_or_create_db, save_forecast

__all__ = ["ProjectForecaster"]

_HAS_STATSMODELS = True
try:
    import numpy as np
    from statsmodels.tsa.api import SimpleExpSmoothing
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel
except ImportError:
    _HAS_STATSMODELS = False

_STATSMODELS_WARNING_SHOWN = False


def _fallback_forecast(
    daily_costs: list[float], baseline_daily: float, baseline_days: int
) -> tuple[float, list[float], list[str]]:
    """Hand-rolled EMA forecast. Used when statsmodels is unavailable."""
    n = len(daily_costs)
    alpha = min(0.6, 0.15 + 0.03 * n)
    smoothed_ratio = 1.0
    for c in daily_costs:
        ratio = c / baseline_daily if baseline_daily > 0 else 1.0
        smoothed_ratio = alpha * ratio + (1 - alpha) * smoothed_ratio

    remaining = max(1, baseline_days - n)
    daily_forecast_val = smoothed_ratio * baseline_daily
    daily_forecasts = [max(0.0, daily_forecast_val)] * remaining
    return smoothed_ratio, daily_forecasts, ["ema_fallback"]


def _ses_forecast(daily_costs: list[float], horizon: int) -> tuple[list[float], list[float] | None]:
    """Simple Exponential Smoothing."""
    n = len(daily_costs)
    arr = np.array(daily_costs, dtype=float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if n < 10:
            model = SimpleExpSmoothing(arr, initialization_method="heuristic")
            fit = model.fit(smoothing_level=0.3, optimized=False)
        else:
            model = SimpleExpSmoothing(arr, initialization_method="estimated")
            fit = model.fit(optimized=True)
    fcast = fit.forecast(horizon)
    residuals = arr - fit.fittedvalues
    return [max(0.0, v) for v in fcast], residuals.tolist()


def _damped_trend_forecast(daily_costs: list[float], horizon: int) -> list[float] | None:
    """Damped Trend ETS. Only used with 10+ data points."""
    if len(daily_costs) < 10:
        return None
    arr = np.array(daily_costs, dtype=float)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ETSModel(arr, error="add", trend="add", damped_trend=True, seasonal=None)
            fit = model.fit(disp=False)
        fcast = fit.forecast(horizon)
        return [max(0.0, v) for v in fcast]
    except Exception:
        return None


def _linear_forecast(daily_costs: list[float], horizon: int) -> list[float] | None:
    """Linear regression forecast."""
    n = len(daily_costs)
    if n < 3:
        return None
    x = np.arange(n, dtype=float)
    y = np.array(daily_costs, dtype=float)
    coeffs = np.polyfit(x, y, 1)
    slope, intercept = coeffs[0], coeffs[1]
    future_x = np.arange(n, n + horizon, dtype=float)
    fcast = intercept + slope * future_x
    return [max(0.0, v) for v in fcast]


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
        actual_spend = sum(daily_costs)
        remaining_days = max(1, self._baseline_total_days - n)

        # Run forecasting models
        global _STATSMODELS_WARNING_SHOWN
        models_used: list[str] = []
        all_forecasts: list[list[float]] = []
        ses_residuals: list[float] | None = None

        if n >= 2 and _HAS_STATSMODELS:
            try:
                ses_fcast, ses_residuals = _ses_forecast(daily_costs, remaining_days)
                all_forecasts.append(ses_fcast)
                models_used.append("ses")
            except Exception:
                pass

            dt_fcast = _damped_trend_forecast(daily_costs, remaining_days)
            if dt_fcast is not None:
                all_forecasts.append(dt_fcast)
                models_used.append("damped_trend")

            lr_fcast = _linear_forecast(daily_costs, remaining_days)
            if lr_fcast is not None:
                all_forecasts.append(lr_fcast)
                models_used.append("linear")

        if not all_forecasts:
            if not _STATSMODELS_WARNING_SHOWN and not _HAS_STATSMODELS and n >= 2:
                _STATSMODELS_WARNING_SHOWN = True
            smoothed_ratio, daily_forecasts, models_used = _fallback_forecast(
                daily_costs, baseline_daily, self._baseline_total_days
            )
        else:
            # Equal-weight ensemble (M4 "Comb" method)
            daily_forecasts = []
            for h in range(remaining_days):
                vals = [f[h] for f in all_forecasts if h < len(f)]
                daily_forecasts.append(sum(vals) / len(vals) if vals else 0.0)
            avg_daily = sum(daily_forecasts) / len(daily_forecasts) if daily_forecasts else 0.0
            smoothed_ratio = avg_daily / baseline_daily if baseline_daily > 0 else 1.0

        projected_remaining = sum(daily_forecasts)
        projected_total = actual_spend + projected_remaining

        # Prediction intervals from residuals
        pi_80 = pi_95 = None
        mase = mae_dollars = None
        if ses_residuals and len(ses_residuals) >= 2:
            sigma = (sum(r**2 for r in ses_residuals) / len(ses_residuals)) ** 0.5
            if sigma > 0:
                lower_80 = [
                    max(0.0, daily_forecasts[h] - 1.28 * sigma * math.sqrt(h + 1))
                    for h in range(remaining_days)
                ]
                upper_80 = [
                    daily_forecasts[h] + 1.28 * sigma * math.sqrt(h + 1)
                    for h in range(remaining_days)
                ]
                lower_95 = [
                    max(0.0, daily_forecasts[h] - 1.96 * sigma * math.sqrt(h + 1))
                    for h in range(remaining_days)
                ]
                upper_95 = [
                    daily_forecasts[h] + 1.96 * sigma * math.sqrt(h + 1)
                    for h in range(remaining_days)
                ]
                pi_80 = {
                    "lower": actual_spend + sum(lower_80),
                    "upper": actual_spend + sum(upper_80),
                }
                pi_95 = {
                    "lower": actual_spend + sum(lower_95),
                    "upper": actual_spend + sum(upper_95),
                }

            # MASE: compare model MAE to naive (random walk) MAE
            model_mae = sum(abs(r) for r in ses_residuals) / len(ses_residuals)
            if n >= 3:
                naive_errors = [abs(daily_costs[i] - daily_costs[i - 1]) for i in range(1, n)]
                naive_mae = sum(naive_errors) / len(naive_errors) if naive_errors else 1.0
                mase = model_mae / naive_mae if naive_mae > 0 else None

            mae_dollars = model_mae * remaining_days

        # Per-model breakdown
        conn = get_or_create_db()
        model_rows = conn.execute(
            "SELECT model, SUM(cost_usd) AS cost FROM usage_logs "
            "WHERE project_id = ? GROUP BY model",
            (self._project_id,),
        ).fetchall()
        model_breakdown = []
        if actual_spend > 0:
            for r in model_rows:
                spent = float(r["cost"])
                share = spent / actual_spend
                projected = spent + share * projected_remaining
                model_breakdown.append(
                    {"model": r["model"], "spent": spent, "projected": projected, "share": share}
                )

        # Drift detection
        daily_burn_ratios = [c / baseline_daily for c in daily_costs] if baseline_daily > 0 else []
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

        # Confidence
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

        # Stability
        stability = stability_label = None
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
                remaining_days,
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
            "remaining_days": remaining_days,
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
            "prediction_interval_80": pi_80,
            "prediction_interval_95": pi_95,
            "mase": mase,
            "mae_dollars": mae_dollars,
            "n_models_used": len(models_used),
            "models_used": models_used,
        }
