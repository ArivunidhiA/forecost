from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from forecost.evidence_profiles import (
    BUILTIN_PROFILES,
    PROVIDER_BILLED_V1,
    ClaimProfile,
    ClaimState,
    Completeness,
    Contradiction,
    EvidenceObligation,
    EvidenceSignal,
    Freshness,
    assess_claim,
)

NOW = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)


def _signal(key: str, role: str, **overrides) -> EvidenceSignal:
    values = {
        "obligation_key": key,
        "source_role": role,
        "observed_at": NOW,
        "finality": "settled",
        "closed": True,
        "contradictory": False,
    }
    values.update(overrides)
    return EvidenceSignal(**values)


def test_user_import_cannot_satisfy_provider_billed_profile():
    assessment = assess_claim(
        PROVIDER_BILLED_V1,
        [
            _signal("authenticated_settlement", "user_imported_claim"),
            _signal("billing_scope_join", "reconciler"),
        ],
        as_of=NOW,
    )

    assert assessment.state is ClaimState.PARTIAL
    assert assessment.denominator == 2
    assert assessment.satisfied == 1
    assert assessment.unmet_obligations == ("authenticated_settlement",)
    assert "source_role_mismatch" in assessment.reason_codes


def test_authenticated_provider_profile_reports_exact_denominator_without_inventing_freshness():
    assessment = assess_claim(
        PROVIDER_BILLED_V1,
        [
            _signal("authenticated_settlement", "provider_authenticated"),
            _signal("billing_scope_join", "reconciler"),
        ],
        as_of=NOW,
    )

    assert assessment.state is ClaimState.UNKNOWN
    assert assessment.completeness is Completeness.COMPLETE
    assert assessment.freshness is Freshness.UNKNOWN
    assert assessment.contradiction is Contradiction.CLEAR
    assert assessment.as_dict()["denominator"] == 2
    assert assessment.as_dict()["unmet_obligations"] == []
    assert assessment.as_dict()["as_of"] == NOW.isoformat()
    obligations = cast(list[dict[str, object]], assessment.as_dict()["obligations"])
    assert obligations[0]["required_source_roles"] == ["provider_authenticated"]
    assert obligations[0]["required_finalities"] == ["settled"]
    assert obligations[0]["fresh"] is None
    assert obligations[0]["reason_code"] == "satisfied_freshness_not_declared"


def test_every_builtin_profile_keeps_version_one_and_abstains_on_freshness_without_an_sla():
    for profile in BUILTIN_PROFILES.values():
        signals = [
            EvidenceSignal(
                obligation.key,
                obligation.source_roles[0],
                NOW,
                finality=(
                    obligation.allowed_finalities[0]
                    if obligation.allowed_finalities
                    else "observed"
                ),
                closed=True,
            )
            for obligation in profile.obligations
        ]

        assessment = assess_claim(profile, signals, as_of=NOW)

        assert assessment.profile_version == 1
        assert assessment.completeness is Completeness.COMPLETE
        assert assessment.freshness is Freshness.UNKNOWN
        assert assessment.contradiction is Contradiction.CLEAR
        assert assessment.state is ClaimState.UNKNOWN


def test_freshness_is_independent_from_completeness():
    profile = ClaimProfile(
        "freshness-test",
        1,
        (EvidenceObligation("heartbeat", "Recorder heartbeat.", ("runtime",), max_age_seconds=5),),
    )
    assessment = assess_claim(
        profile,
        [_signal("heartbeat", "runtime", observed_at=NOW - timedelta(seconds=6))],
        as_of=NOW,
    )

    assert assessment.completeness is Completeness.COMPLETE
    assert assessment.freshness is Freshness.STALE
    assert assessment.state is ClaimState.STALE


def test_partial_assessment_preserves_known_staleness_on_separate_axis():
    profile = ClaimProfile(
        "partial-stale-test",
        1,
        (
            EvidenceObligation(
                "heartbeat",
                "Recorder heartbeat.",
                ("runtime",),
                max_age_seconds=5,
            ),
            EvidenceObligation("closure", "Run closure.", ("runtime",)),
        ),
    )
    assessment = assess_claim(
        profile,
        [_signal("heartbeat", "runtime", observed_at=NOW - timedelta(seconds=6))],
        as_of=NOW,
    )

    assert assessment.completeness is Completeness.PARTIAL
    assert assessment.freshness is Freshness.STALE
    assert assessment.contradiction is Contradiction.UNKNOWN
    assert assessment.state is ClaimState.PARTIAL


def test_contradiction_precedes_complete_and_stale_states():
    profile = ClaimProfile(
        "conflict-test",
        1,
        (EvidenceObligation("meter", "Final meter.", ("runtime",)),),
    )
    assessment = assess_claim(
        profile,
        [_signal("meter", "runtime", contradictory=True)],
        as_of=NOW,
    )

    assert assessment.contradiction is Contradiction.CONTRADICTORY
    assert assessment.state is ClaimState.CONTRADICTORY
    assert assessment.completeness is Completeness.PARTIAL


def test_removing_required_evidence_never_improves_complete_assessment():
    full = [
        _signal("authenticated_settlement", "provider_authenticated"),
        _signal("billing_scope_join", "reconciler"),
    ]
    full_assessment = assess_claim(PROVIDER_BILLED_V1, full, as_of=NOW)
    assert full_assessment.completeness is Completeness.COMPLETE
    assert full_assessment.freshness is Freshness.UNKNOWN

    for index in range(len(full)):
        reduced = assess_claim(PROVIDER_BILLED_V1, full[:index] + full[index + 1 :], as_of=NOW)
        assert reduced.completeness is Completeness.PARTIAL
        assert reduced.satisfied < full_assessment.satisfied


def test_unsupported_schema_and_empty_denominator_abstain():
    unsupported = assess_claim(PROVIDER_BILLED_V1, (), as_of=NOW, schema_supported=False)
    empty = assess_claim(ClaimProfile("empty", 1, ()), (), as_of=NOW)

    for assessment in (unsupported, empty):
        assert assessment.state is ClaimState.UNKNOWN
        assert assessment.completeness is Completeness.UNKNOWN
        assert assessment.freshness is Freshness.UNKNOWN
        assert assessment.contradiction is Contradiction.UNKNOWN


def test_profile_contract_rejects_ambiguous_or_invalid_denominators():
    obligation = EvidenceObligation("same", "One fact.", ("runtime",))
    with pytest.raises(ValueError, match="unique"):
        ClaimProfile("duplicate", 1, (obligation, obligation))
    with pytest.raises(ValueError, match="source role"):
        EvidenceObligation("missing-source", "One fact.", ())
    with pytest.raises(ValueError, match="timezone-aware"):
        EvidenceSignal("fact", "runtime", NOW.replace(tzinfo=None))


def test_future_timestamp_is_not_fresh():
    profile = ClaimProfile(
        "clock-test",
        1,
        (EvidenceObligation("heartbeat", "Recorder heartbeat.", ("runtime",), max_age_seconds=5),),
    )
    assessment = assess_claim(
        profile,
        [_signal("heartbeat", "runtime", observed_at=NOW + timedelta(seconds=1))],
        as_of=NOW,
    )

    assert assessment.state is ClaimState.STALE
    assert "required_evidence_stale" in assessment.reason_codes
