"""
Ensemble forecasting engine for LLM cost tracking.

Uses a three-model combination (SES + Damped Trend + Linear Regression)
inspired by the M4 Forecasting Competition, where simple combinations
beat all pure ML methods for short time series.

Falls back to hand-rolled EMA when statsmodels is not installed.
"""

from __future__ import annotations

import logging
import math
import warnings
from typing import Any

from forecost.db import (
    get_bucketed_costs,
    get_daily_costs,
    get_forecast_history,
    get_or_create_db,
    save_forecast,
)

__all__ = ["ProjectForecaster"]

logger = logging.getLogger(__name__)

_HAS_STATSMODELS = True
try:
    import numpy as np  # type: ignore[import-untyped]
    from statsmodels.tsa.api import SimpleExpSmoothing  # type: ignore[import-untyped]
    from statsmodels.tsa.exponential_smoothing.ets import ETSModel  # type: ignore[import-untyped]
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
    arr = np.array(daily_costs, dtype=float)  # type: ignore[union-attr]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if n < 10:
            model = SimpleExpSmoothing(arr, initialization_method="heuristic")  # type: ignore[union-attr]
            fit = model.fit(smoothing_level=0.3, optimized=False)
        else:
            model = SimpleExpSmoothing(arr, initialization_method="estimated")  # type: ignore[union-attr]
            fit = model.fit(optimized=True)
    fcast = fit.forecast(horizon)
    residuals = arr - fit.fittedvalues
    return [max(0.0, v) for v in fcast], residuals.tolist()


def _damped_trend_forecast(daily_costs: list[float], horizon: int) -> list[float] | None:
    """Damped Trend ETS. Only used with 10+ data points."""
    if len(daily_costs) < 10:
        return None
    arr = np.array(daily_costs, dtype=float)  # type: ignore[union-attr]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ETSModel(arr, error="add", trend="add", damped_trend=True, seasonal=None)  # type: ignore[union-attr]
            fit: Any = model.fit(disp=False)
        fcast = fit.forecast(horizon)
        return [max(0.0, v) for v in fcast]
    except Exception:
        return None


def _linear_forecast(daily_costs: list[float], horizon: int) -> list[float] | None:
    """Linear regression forecast."""
    n = len(daily_costs)
    if n < 3:
        return None
    x = np.arange(n, dtype=float)  # type: ignore[union-attr]
    y = np.array(daily_costs, dtype=float)  # type: ignore[union-attr]
    coeffs = np.polyfit(x, y, 1)  # type: ignore[union-attr]
    slope, intercept = coeffs[0], coeffs[1]
    future_x = np.arange(n, n + horizon, dtype=float)  # type: ignore[union-attr]
    fcast = intercept + slope * future_x
    return [max(0.0, v) for v in fcast]


def _select_series(
    daily_costs: list[float],
    bucketed_costs: list[tuple[str, float, int]],
    n_days: int,
) -> tuple[list[float], bool, int]:
    bucket_costs_raw = [(b, cost) for b, cost, _tokens in bucketed_costs if cost > 0]
    n_buckets = len(bucket_costs_raw)
    bucket_costs = [c for _, c in bucket_costs_raw]
    use_buckets = n_buckets >= 3 and n_buckets > n_days
    return (bucket_costs if use_buckets else daily_costs), use_buckets, n_buckets


def _forecast_horizon(
    *, use_buckets: bool, n_buckets: int, n_days: int, remaining_days: int
) -> tuple[int, float]:
    if use_buckets:
        active_days_for_rate = max(1, n_days)
        buckets_per_day = n_buckets / active_days_for_rate
        return n_buckets, buckets_per_day
    return remaining_days, 1.0


def _run_model_ensemble(
    *,
    series: list[float],
    forecast_horizon: int,
    baseline_daily: float,
    baseline_total_days: int,
) -> tuple[float, float, list[str], list[float] | None]:
    global _STATSMODELS_WARNING_SHOWN

    n = len(series)
    models_used: list[str] = []
    all_forecasts: list[list[float]] = []
    ses_residuals: list[float] | None = None

    if n >= 2 and _HAS_STATSMODELS:
        ses_residuals = _append_ses_forecast(series, forecast_horizon, all_forecasts, models_used)
        _append_optional_forecast(
            _damped_trend_forecast(series, forecast_horizon),
            "damped_trend",
            all_forecasts,
            models_used,
        )
        _append_optional_forecast(
            _linear_forecast(series, forecast_horizon),
            "linear",
            all_forecasts,
            models_used,
        )

    if not all_forecasts:
        if not _STATSMODELS_WARNING_SHOWN and not _HAS_STATSMODELS and n >= 2:
            _STATSMODELS_WARNING_SHOWN = True
        smoothed_ratio, period_forecasts, models_used = _fallback_forecast(
            series, baseline_daily, baseline_total_days
        )
        return sum(period_forecasts), smoothed_ratio, models_used, ses_residuals

    period_forecasts = _combine_ensemble_forecasts(all_forecasts, forecast_horizon)

    projected_remaining = sum(period_forecasts)
    avg_daily = projected_remaining / max(1, forecast_horizon)
    smoothed_ratio = avg_daily / baseline_daily if baseline_daily > 0 else 1.0
    return projected_remaining, smoothed_ratio, models_used, ses_residuals


def _append_ses_forecast(
    series: list[float],
    forecast_horizon: int,
    all_forecasts: list[list[float]],
    models_used: list[str],
) -> list[float] | None:
    try:
        ses_fcast, ses_residuals = _ses_forecast(series, forecast_horizon)
        all_forecasts.append(ses_fcast)
        models_used.append("ses")
        return ses_residuals
    except Exception as e:
        logger.debug(f"SES forecast failed, skipping model: {e}")
        return None


def _append_optional_forecast(
    forecast: list[float] | None,
    model_name: str,
    all_forecasts: list[list[float]],
    models_used: list[str],
) -> None:
    if forecast is None:
        return
    all_forecasts.append(forecast)
    models_used.append(model_name)


def _combine_ensemble_forecasts(
    all_forecasts: list[list[float]], forecast_horizon: int
) -> list[float]:
    period_forecasts: list[float] = []
    for h in range(forecast_horizon):
        vals = [f[h] for f in all_forecasts if h < len(f)]
        period_forecasts.append(sum(vals) / len(vals) if vals else 0.0)
    return period_forecasts


def _convert_bucket_projection(
    *,
    projected_remaining: float,
    forecast_horizon: int,
    buckets_per_day: float,
    remaining_days: int,
) -> float:
    if forecast_horizon <= 0:
        return 0.0
    avg_forecast_per_bucket = projected_remaining / forecast_horizon
    projected_daily = avg_forecast_per_bucket * buckets_per_day
    return projected_daily * remaining_days


def _prediction_intervals(
    *,
    ses_residuals: list[float] | None,
    use_buckets: bool,
    buckets_per_day: float,
    projected_remaining: float,
    remaining_days: int,
    actual_spend: float,
    series: list[float],
) -> tuple[dict | None, dict | None, float | None, float | None]:
    if not ses_residuals or len(ses_residuals) < 2:
        return None, None, None, None

    sigma = (sum(r**2 for r in ses_residuals) / len(ses_residuals)) ** 0.5
    pi_80, pi_95 = _build_prediction_bands(
        sigma=sigma,
        use_buckets=use_buckets,
        buckets_per_day=buckets_per_day,
        projected_remaining=projected_remaining,
        remaining_days=remaining_days,
        actual_spend=actual_spend,
    )

    model_mae = sum(abs(r) for r in ses_residuals) / len(ses_residuals)
    mase = _compute_mase(series, model_mae)
    mae_dollars = model_mae * remaining_days
    return pi_80, pi_95, mase, mae_dollars


def _build_prediction_bands(
    *,
    sigma: float,
    use_buckets: bool,
    buckets_per_day: float,
    projected_remaining: float,
    remaining_days: int,
    actual_spend: float,
) -> tuple[dict | None, dict | None]:
    if sigma <= 0:
        return None, None

    daily_sigma = sigma * math.sqrt(buckets_per_day) if use_buckets else sigma
    dm = projected_remaining / max(1, remaining_days)
    lower_80 = [max(0.0, dm - 1.28 * daily_sigma * math.sqrt(h + 1)) for h in range(remaining_days)]
    upper_80 = [dm + 1.28 * daily_sigma * math.sqrt(h + 1) for h in range(remaining_days)]
    lower_95 = [max(0.0, dm - 1.96 * daily_sigma * math.sqrt(h + 1)) for h in range(remaining_days)]
    upper_95 = [dm + 1.96 * daily_sigma * math.sqrt(h + 1) for h in range(remaining_days)]
    pi_80 = {"lower": actual_spend + sum(lower_80), "upper": actual_spend + sum(upper_80)}
    pi_95 = {"lower": actual_spend + sum(lower_95), "upper": actual_spend + sum(upper_95)}
    return pi_80, pi_95


def _compute_mase(series: list[float], model_mae: float) -> float | None:
    if len(series) < 3:
        return None
    naive_errors = [abs(series[i] - series[i - 1]) for i in range(1, len(series))]
    naive_mae = sum(naive_errors) / len(naive_errors) if naive_errors else 1.0
    return model_mae / naive_mae if naive_mae > 0 else None


def _model_breakdown(
    project_id: int, actual_spend: float, projected_remaining: float
) -> list[dict]:
    conn = get_or_create_db()
    rows = conn.execute(
        "SELECT model, SUM(cost_usd) AS cost FROM usage_logs WHERE project_id = ? GROUP BY model",
        (project_id,),
    ).fetchall()
    if actual_spend <= 0:
        return []

    breakdown: list[dict] = []
    for row in rows:
        spent = float(row["cost"])
        share = spent / actual_spend
        projected = spent + share * projected_remaining
        breakdown.append(
            {"model": row["model"], "spent": spent, "projected": projected, "share": share}
        )
    return breakdown


def _drift_status(daily_costs: list[float], baseline_daily: float, smoothed_ratio: float) -> str:
    daily_burn_ratios = [c / baseline_daily for c in daily_costs] if baseline_daily > 0 else []
    last_n = min(len(daily_burn_ratios), 5)
    last_ratios = daily_burn_ratios[-last_n:] if daily_burn_ratios else []

    consecutive_over = _count_consecutive(last_ratios, lambda ratio: ratio > 1.5)
    consecutive_under = _count_consecutive(last_ratios, lambda ratio: ratio < 0.5)

    if smoothed_ratio > 1.5 and consecutive_over >= 3:
        return "over_budget"
    if smoothed_ratio < 0.5 and consecutive_under >= 3:
        return "under_budget"
    return "on_track"


def _count_consecutive(values: list[float], predicate) -> int:
    count = 0
    for value in reversed(values):
        if not predicate(value):
            break
        count += 1
    return count


def _confidence_for_days(n_days: int) -> str:
    if n_days == 0:
        return "low"
    if n_days <= 3:
        return "medium-low"
    if n_days <= 7:
        return "medium"
    if n_days <= 14:
        return "high"
    return "very-high"


def _stability_info(history: list[dict], projected_total: float) -> tuple[float | None, str | None]:
    history_totals = [h["projected_total"] for h in history]
    history_totals.append(projected_total)
    recent = history_totals[-5:]
    if len(recent) < 2:
        return None, None

    changes = [
        abs(recent[i] - recent[i - 1]) / max(recent[i], 0.001) * 100 for i in range(1, len(recent))
    ]
    if not changes:
        return None, None

    stability = sum(changes) / len(changes)
    if stability < 5:
        return stability, "converged"
    if stability <= 15:
        return stability, "stabilizing"
    return stability, "adjusting"


class ProjectForecaster:
    """Compute budget forecasts for a single project.

    Args:
        project_id: Project id to forecast.
    """

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
        self._bucketed_costs, self._bucket_minutes = self._adaptive_buckets(project_id)
        self._forecast_history = get_forecast_history(project_id)

    @staticmethod
    def _adaptive_buckets(project_id: int) -> tuple[list[tuple[str, float, int]], int]:
        """Try progressively finer bucket granularity until we get >= 3 data points."""
        buckets: list[tuple[str, float, int]] = []
        minutes: int = 1
        for minutes in (15, 5, 1):
            buckets = get_bucketed_costs(project_id, bucket_minutes=minutes)
            active = [(b, c) for b, c, _t in buckets if c > 0]
            if len(active) >= 3:
                return buckets, minutes
        return buckets, minutes

    def calculate_forecast(self, *, save: bool = False) -> dict:
        """Calculate forecast metrics for the configured project.

        Args:
            save: Whether to persist the computed forecast iteration.

        Returns:
            dict: Forecast payload including projections, confidence, and model diagnostics.
        """
        active_days_data = [(day, cost) for day, cost, _tokens in self._daily_costs if cost > 0]
        n_days = len(active_days_data)
        daily_costs = [c for _, c in active_days_data]
        series, use_buckets, n_buckets = _select_series(daily_costs, self._bucketed_costs, n_days)
        n = len(series)

        baseline_daily = self._baseline_daily_cost if self._baseline_daily_cost > 0 else 1.0
        actual_spend = sum(daily_costs)
        total_tokens = sum(tokens for _, _, tokens in self._daily_costs)
        remaining_days = max(1, self._baseline_total_days - n_days)
        forecast_horizon, buckets_per_day = _forecast_horizon(
            use_buckets=use_buckets,
            n_buckets=n_buckets,
            n_days=n_days,
            remaining_days=remaining_days,
        )

        projected_remaining, smoothed_ratio, models_used, ses_residuals = _run_model_ensemble(
            series=series,
            forecast_horizon=forecast_horizon,
            baseline_daily=baseline_daily,
            baseline_total_days=self._baseline_total_days,
        )

        if use_buckets:
            projected_remaining = _convert_bucket_projection(
                projected_remaining=projected_remaining,
                forecast_horizon=forecast_horizon,
                buckets_per_day=buckets_per_day,
                remaining_days=remaining_days,
            )
            avg_daily = projected_remaining / max(1, remaining_days)
            smoothed_ratio = avg_daily / baseline_daily if baseline_daily > 0 else 1.0

        projected_total = actual_spend + projected_remaining
        pi_80, pi_95, mase, mae_dollars = _prediction_intervals(
            ses_residuals=ses_residuals,
            use_buckets=use_buckets,
            buckets_per_day=buckets_per_day,
            projected_remaining=projected_remaining,
            remaining_days=remaining_days,
            actual_spend=actual_spend,
            series=series,
        )

        model_breakdown = _model_breakdown(self._project_id, actual_spend, projected_remaining)
        drift_status = _drift_status(daily_costs, baseline_daily, smoothed_ratio)
        confidence = _confidence_for_days(n_days)
        stability, stability_label = _stability_info(self._forecast_history, projected_total)

        iteration = len(self._forecast_history) + 1

        if save:
            save_forecast(
                self._project_id,
                iteration,
                projected_total,
                remaining_days,
                smoothed_ratio,
                confidence,
                n_days,
                mase,
            )

        return {
            "project_id": self._project_id,
            "project_name": self._project_name,
            "actual_spend": actual_spend,
            "total_tokens": total_tokens,
            "projected_total": projected_total,
            "projected_remaining": projected_remaining,
            "remaining_days": remaining_days,
            "active_days": n_days,
            "data_points": n,
            "data_granularity": f"{self._bucket_minutes}min_buckets" if use_buckets else "daily",
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
