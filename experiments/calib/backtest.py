"""Rolling-origin backtest for the Forecost calibration gates (G-A, G-R1, G-R2, G-R3).

Reads turns.db (produced by extract.py) and evaluates whether calibrated P10/P50/P90
quantile estimates — built only from a user's own prior history — hold their coverage
on unseen future turns. Implements the protocol in round3-estimation.md §6 and the
extension in round5-risk.md §5.

Targets: cost (T1), duration (T5), files_touched (T-extra, G-R1).
Methods: B0 (global quantiles), B1 (per-category quantiles), M1 (hierarchical
empirical quantiles with shrinkage toward the parent category/global).
Also computes: G-R2 (success-rate separation by category) and G-R3 (retrospective
precision of a simple rule-based stuck/error detector).

No network calls, no ML dependencies beyond numpy (already a common local dependency;
falls back gracefully if unavailable is not implemented here since numpy is stdlib-
adjacent on this machine and the plan's constraint is "scikit-learn-class", not
"stdlib-only" for the experiment — hooks/fastpath remain stdlib-only per Phase 1).
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

BURN_IN = 40
SHRINK_K = 10  # empirical-Bayes shrinkage constant (round3-estimation §3.1)


@dataclass
class Quantiles:
    p10: float
    p50: float
    p90: float
    n: int


def _log_quantiles(values: list[float]) -> tuple[float, float, float]:
    logs = [math.log1p(max(0.0, v)) for v in values]
    arr = np.array(logs)
    q10, q50, q90 = np.quantile(arr, [0.10, 0.50, 0.90])
    return float(q10), float(q50), float(q90)


def _expm1_clip(x: float) -> float:
    return max(0.0, math.expm1(x))


def hierarchical_quantiles(
    train_values: list[float], train_categories: list[str], target_category: str
) -> Quantiles:
    """M1: category quantiles shrunk toward the global quantiles by n/(n+k)."""
    global_q10, global_q50, global_q90 = _log_quantiles(train_values) if train_values else (0, 0, 0)
    cell_values = [v for v, c in zip(train_values, train_categories) if c == target_category]
    n = len(cell_values)
    if n < 3:
        return Quantiles(_expm1_clip(global_q10), _expm1_clip(global_q50), _expm1_clip(global_q90), n)
    cell_q10, cell_q50, cell_q90 = _log_quantiles(cell_values)
    w = n / (n + SHRINK_K)
    q10 = w * cell_q10 + (1 - w) * global_q10
    q50 = w * cell_q50 + (1 - w) * global_q50
    q90 = w * cell_q90 + (1 - w) * global_q90
    return Quantiles(_expm1_clip(q10), _expm1_clip(q50), _expm1_clip(q90), n)


def global_quantiles(train_values: list[float]) -> Quantiles:
    if not train_values:
        return Quantiles(0, 0, 0, 0)
    q10, q50, q90 = _log_quantiles(train_values)
    return Quantiles(_expm1_clip(q10), _expm1_clip(q50), _expm1_clip(q90), len(train_values))


def category_quantiles(
    train_values: list[float], train_categories: list[str], target_category: str
) -> Quantiles:
    cell_values = [v for v, c in zip(train_values, train_categories) if c == target_category]
    if len(cell_values) < 3:
        return Quantiles(0, 0, 0, 0)
    q10, q50, q90 = _log_quantiles(cell_values)
    return Quantiles(_expm1_clip(q10), _expm1_clip(q50), _expm1_clip(q90), len(cell_values))


def pinball_loss(actual: float, quoted: float, tau: float) -> float:
    diff = actual - quoted
    return max(tau * diff, (tau - 1) * diff)


def run_target_backtest(rows: list[dict], target: str) -> dict:
    """Rolling-origin backtest for one target column. Returns a metrics dict per method."""
    results = {
        "B0": {"cover90": [], "cover50": [], "pinball50": [], "pinball90": [], "widths": []},
        "B1": {"cover90": [], "cover50": [], "pinball50": [], "pinball90": [], "widths": []},
        "M1": {"cover90": [], "cover50": [], "pinball50": [], "pinball90": [], "widths": []},
    }
    per_category: dict[str, dict] = {}

    for i in range(BURN_IN, len(rows)):
        train = rows[:i]
        test = rows[i]
        train_values = [r[target] for r in train]
        train_categories = [r["category"] for r in train]
        actual = test[target]
        cat = test["category"]

        b0 = global_quantiles(train_values)
        b1 = category_quantiles(train_values, train_categories, cat)
        m1 = hierarchical_quantiles(train_values, train_categories, cat)

        for name, q in (("B0", b0), ("B1", b1), ("M1", m1)):
            if q.n == 0 or (name == "B1" and q.p90 == 0 and q.p50 == 0):
                continue  # sparse cell, method abstains
            results[name]["cover90"].append(1 if actual <= q.p90 else 0)
            results[name]["cover50"].append(1 if actual <= q.p50 else 0)
            results[name]["pinball50"].append(pinball_loss(actual, q.p50, 0.5))
            results[name]["pinball90"].append(pinball_loss(actual, q.p90, 0.9))
            if q.p50 > 0:
                results[name]["widths"].append(q.p90 / max(q.p50, 1e-6))

            if name == "M1":
                cell = per_category.setdefault(
                    cat, {"cover90": [], "widths": [], "n_train": []}
                )
                cell["cover90"].append(1 if actual <= q.p90 else 0)
                if q.p50 > 0:
                    cell["widths"].append(q.p90 / max(q.p50, 1e-6))
                cell["n_train"].append(q.n)

    summary = {}
    for name, m in results.items():
        n_eval = len(m["cover90"])
        if n_eval == 0:
            summary[name] = {"n_eval": 0}
            continue
        summary[name] = {
            "n_eval": n_eval,
            "coverage_p90": round(float(np.mean(m["cover90"])), 4),
            "coverage_p50": round(float(np.mean(m["cover50"])), 4),
            "median_pinball50": round(float(np.median(m["pinball50"])), 4),
            "median_pinball90": round(float(np.median(m["pinball90"])), 4),
            "median_width_p90_p50": round(float(np.median(m["widths"])), 4) if m["widths"] else None,
        }

    # skill: M1 pinball90 improvement over B0 pinball90
    if summary["M1"].get("n_eval") and summary["B0"].get("n_eval"):
        b0p = summary["B0"]["median_pinball90"]
        m1p = summary["M1"]["median_pinball90"]
        skill = (b0p - m1p) / b0p if b0p > 0 else 0.0
        summary["M1"]["skill_vs_B0_pinball90"] = round(skill, 4)

    per_cat_summary = {}
    for cat, cell in per_category.items():
        if len(cell["cover90"]) < 5:
            continue
        per_cat_summary[cat] = {
            "n_eval": len(cell["cover90"]),
            "avg_n_train": round(float(np.mean(cell["n_train"])), 1),
            "coverage_p90": round(float(np.mean(cell["cover90"])), 4),
            "median_width": round(float(np.median(cell["widths"])), 4) if cell["widths"] else None,
        }
    summary["per_category"] = per_cat_summary
    return summary


def run_gate_ga(rows: list[dict]) -> dict:
    verdicts = {}
    for target, label in (
        ("cost_usd_api_equiv", "cost"),
        ("duration_s", "duration"),
        ("files_touched", "files"),
    ):
        bt = run_target_backtest(rows, target)
        m1 = bt.get("M1", {})
        if not m1.get("n_eval"):
            verdicts[label] = {"verdict": "INSUFFICIENT-DATA", "backtest": bt}
            continue
        cov90 = m1.get("coverage_p90", 0)
        width = m1.get("median_width_p90_p50")
        skill = m1.get("skill_vs_B0_pinball90", 0)
        worst_cell_cov = min(
            (c["coverage_p90"] for c in bt["per_category"].values()), default=None
        )
        pass_width = width is not None and (
            (width <= 4 if label == "cost" else width <= 5)
        )
        pass_cov = 0.85 <= cov90 <= 0.95
        pass_worst = worst_cell_cov is None or worst_cell_cov >= 0.75
        pass_skill = skill >= 0.15 if label == "cost" else skill >= 0.10
        if pass_cov and pass_width and pass_worst and pass_skill:
            verdict = "PASS"
        elif pass_cov and worst_cell_cov is not None and worst_cell_cov >= 0.5:
            verdict = "MARGINAL"
        else:
            verdict = "FAIL"
        verdicts[label] = {
            "verdict": verdict,
            "coverage_p90": cov90,
            "median_width_p90_p50": width,
            "skill_vs_B0": skill,
            "worst_cell_coverage": worst_cell_cov,
            "n_eval": m1["n_eval"],
            "backtest": bt,
        }
    return verdicts


def run_gate_gr2(rows: list[dict]) -> dict:
    """G-R2: does weak-labeled success rate separate meaningfully by category?"""
    from collections import defaultdict

    by_cat = defaultdict(list)
    for r in rows:
        if r["weak_outcome"] in ("ok", "fail"):
            by_cat[r["category"]].append(1 if r["weak_outcome"] == "ok" else 0)

    rates = {}
    for cat, outcomes in by_cat.items():
        n = len(outcomes)
        if n < 15:
            continue
        rate = sum(outcomes) / n
        # Wilson 90% CI
        z = 1.645
        denom = 1 + z**2 / n
        centre = (rate + z**2 / (2 * n)) / denom
        margin = (z * math.sqrt(rate * (1 - rate) / n + z**2 / (4 * n**2))) / denom
        rates[cat] = {
            "n": n,
            "success_rate": round(rate, 4),
            "wilson_90_lo": round(centre - margin, 4),
            "wilson_90_hi": round(centre + margin, 4),
        }

    max_sep = 0.0
    cats = list(rates.keys())
    for i in range(len(cats)):
        for j in range(i + 1, len(cats)):
            a, b = rates[cats[i]], rates[cats[j]]
            if a["wilson_90_hi"] < b["wilson_90_lo"] or b["wilson_90_hi"] < a["wilson_90_lo"]:
                sep = abs(a["success_rate"] - b["success_rate"])
                max_sep = max(max_sep, sep)

    n_fail_total = sum(1 for r in rows if r["weak_outcome"] == "fail")
    n_ok_total = sum(1 for r in rows if r["weak_outcome"] == "ok")

    if n_fail_total < 5:
        verdict = "INSUFFICIENT-DATA"
        note = f"Only {n_fail_total} weak-labeled failures in the whole corpus ({n_ok_total} ok, " \
               f"{len(rows) - n_fail_total - n_ok_total} ambiguous) — the corpus is too healthy " \
               "to learn a failure signal from (round5-risk §6.1's predicted outcome)."
    elif len(rates) >= 2 and max_sep >= 0.20:
        verdict = "PASS"
        note = f"Max separating gap between qualified categories: {max_sep:.1%}"
    else:
        verdict = "FAIL"
        note = f"No pair of qualified categories (n>=15) separates by >=20pp with non-overlapping CIs (max gap {max_sep:.1%})."

    return {
        "verdict": verdict,
        "note": note,
        "rates_by_category": rates,
        "n_fail_total": n_fail_total,
        "n_ok_total": n_ok_total,
        "n_ambiguous_total": len(rows) - n_fail_total - n_ok_total,
    }


def run_gate_gr3(rows: list[dict]) -> dict:
    """G-R3: retrospective precision of a rule-based stuck/error detector.

    Rule: flag a turn if max_consec_errors >= 3 OR tail_error_flag=1 with
    error_result_count >= 2. Precision = P(weak_outcome != ok | flagged).
    """
    flagged = [
        r for r in rows
        if r["max_consec_errors"] >= 3 or (r["tail_error_flag"] and r["error_result_count"] >= 2)
    ]
    flag_rate = len(flagged) / len(rows) if rows else 0
    if not flagged:
        return {
            "verdict": "INSUFFICIENT-DATA",
            "note": "Detector rule never fired on this corpus (0 flagged turns) — "
                    "cannot measure precision. Consistent with round5-risk's low error-loop base rate.",
            "flag_rate": flag_rate,
            "n_flagged": 0,
        }
    non_ok = sum(1 for r in flagged if r["weak_outcome"] != "ok")
    precision = non_ok / len(flagged)
    pass_ = precision >= 0.60 and flag_rate <= 0.10
    return {
        "verdict": "PASS" if pass_ else "FAIL",
        "precision": round(precision, 4),
        "flag_rate": round(flag_rate, 4),
        "n_flagged": len(flagged),
        "note": f"{len(flagged)}/{len(rows)} turns flagged ({flag_rate:.1%}); "
                f"{non_ok}/{len(flagged)} of flagged turns were non-ok ({precision:.1%} precision).",
    }


def load_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM turns ORDER BY ts_start").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main() -> None:
    db_path = Path(__file__).parent / "turns.db"
    rows = load_rows(db_path)
    print(f"Loaded {len(rows)} turns from {db_path}\n")

    ga = run_gate_ga(rows)
    gr2 = run_gate_gr2(rows)
    gr3 = run_gate_gr3(rows)

    report = {
        "n_turns": len(rows),
        "n_categories": len(set(r["category"] for r in rows)),
        "gate_G_A": ga,
        "gate_G_R2": gr2,
        "gate_G_R3": gr3,
    }

    out_path = Path(__file__).parent / "verdict.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print("=" * 70)
    print("GATE G-A / G-R1 (cost, duration, files — coverage/width/skill)")
    print("=" * 70)
    for label, v in ga.items():
        print(f"\n[{label}] verdict: {v['verdict']}")
        if v["verdict"] != "INSUFFICIENT-DATA":
            print(f"  coverage_p90={v['coverage_p90']}  width={v['median_width_p90_p50']}  "
                  f"skill_vs_B0={v['skill_vs_B0']}  worst_cell_cov={v['worst_cell_coverage']}  "
                  f"n_eval={v['n_eval']}")
            for m in ("B0", "B1", "M1"):
                s = v["backtest"][m]
                if s.get("n_eval"):
                    print(f"    {m}: n={s['n_eval']} cov90={s.get('coverage_p90')} "
                          f"cov50={s.get('coverage_p50')} width={s.get('median_width_p90_p50')} "
                          f"pinball90={s.get('median_pinball90')}")

    print("\n" + "=" * 70)
    print("GATE G-R2 (success-table separation)")
    print("=" * 70)
    print(f"verdict: {gr2['verdict']}")
    print(f"  {gr2['note']}")
    print(f"  ok={gr2['n_ok_total']} fail={gr2['n_fail_total']} ambiguous={gr2['n_ambiguous_total']}")
    for cat, r in gr2["rates_by_category"].items():
        print(f"  {cat}: n={r['n']} rate={r['success_rate']} "
              f"CI=[{r['wilson_90_lo']},{r['wilson_90_hi']}]")

    print("\n" + "=" * 70)
    print("GATE G-R3 (mid-run guard retrospective precision)")
    print("=" * 70)
    print(f"verdict: {gr3['verdict']}")
    print(f"  {gr3['note']}")

    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
