"""Golden snapshot of `compare` decisions: strictness cannot drift silently.

Any behavior change in forecost/comparison.py that flips a decision or reason code makes
this test fail. To accept an intentional change, regenerate the snapshot, review the diff,
and commit it together with the code change:

    UPDATE_COMPARISON_GOLDEN=1 pytest tests/test_comparison_golden.py

CI additionally fails a PR that edits comparison.py without touching a test or this snapshot
(scripts/check_comparison_guard.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from forecost.comparison import ComparisonConfigurationError, compare_manifests
from tests.test_comparison import _cohort, _decision

GOLDEN = Path(__file__).parent / "golden" / "compare_v1.json"

SCENARIOS: dict[str, dict[str, Any]] = {
    "qualified_30_pairs": {},
    "roster_smaller_than_min_pairs": {"count": 5},
    "candidate_not_cheaper": {"candidate_amount": 100_000},
    "candidate_outcome_regresses": {"candidate_status": "bad"},
    "tariff_scope_mismatch": {"candidate_tariff": "tariff-v2"},
    "empty_tariff": {"baseline_tariff_payload": {}, "candidate_tariff_payload": {}},
    "tariff_without_rate_snapshot": {
        "baseline_tariff_payload": {"discount": False},
        "candidate_tariff_payload": {"discount": False},
    },
    "unbound_charge": {"candidate_bind_charge_to_meter": False},
    "weak_outcome_confidence": {"candidate_outcome_confidence": "unknown"},
}


def _snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, kwargs in SCENARIOS.items():
        conn, baseline, candidate, policy = _cohort(**kwargs)
        try:
            decision = _decision(compare_manifests(conn, baseline, candidate, policy))
        except ComparisonConfigurationError as error:
            out[name] = {"status": "configuration_error", "reason_codes": [str(error)]}
            continue
        finally:
            conn.close()
        out[name] = {
            "status": decision["status"],
            "reason_codes": sorted(cast(list[str], decision["reason_codes"])),
        }
    return out


def test_comparison_decisions_match_golden_snapshot():
    current = _snapshot()
    if os.environ.get("UPDATE_COMPARISON_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert current == expected


def test_only_the_fully_qualified_cohort_passes():
    statuses = {name: item["status"] for name, item in _snapshot().items()}
    assert statuses["qualified_30_pairs"] == "pass"
    assert all(
        status != "pass" for name, status in statuses.items() if name != "qualified_30_pairs"
    )
