"""Deterministic, predeclared evidence obligations for receipt claims.

This module deliberately does not infer what a caller intended to prove from
the evidence that happened to arrive. A claim profile and its denominator are
declared first; observations are then evaluated against that contract.
Completeness, freshness, and contradiction remain independent axes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Final


class Completeness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class Freshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class Contradiction(str, Enum):
    CLEAR = "clear"
    CONTRADICTORY = "contradictory"
    UNKNOWN = "unknown"


class ClaimState(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"
    CONTRADICTORY = "contradictory"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidenceObligation:
    """One required fact declared before evidence is evaluated."""

    key: str
    description: str
    source_roles: tuple[str, ...]
    allowed_finalities: tuple[str, ...] = ()
    max_age_seconds: int | None = None
    requires_closed: bool = False

    def __post_init__(self) -> None:
        if not self.key or len(self.key) > 80:
            raise ValueError("obligation key must be a non-empty bounded identifier")
        if not self.description or len(self.description) > 240:
            raise ValueError("obligation description must be non-empty and bounded")
        if not self.source_roles:
            raise ValueError("obligation must declare at least one source role")
        if len(set(self.source_roles)) != len(self.source_roles):
            raise ValueError("obligation source roles must be unique")
        if self.max_age_seconds is not None and self.max_age_seconds < 0:
            raise ValueError("obligation max age must be non-negative")


@dataclass(frozen=True)
class ClaimProfile:
    """A versioned denominator for one precise family of claims."""

    profile_id: str
    version: int
    obligations: tuple[EvidenceObligation, ...]

    def __post_init__(self) -> None:
        if not self.profile_id or len(self.profile_id) > 80:
            raise ValueError("profile id must be a non-empty bounded identifier")
        if self.version < 1:
            raise ValueError("profile version must be positive")
        keys = [item.key for item in self.obligations]
        if len(keys) != len(set(keys)):
            raise ValueError("profile obligation keys must be unique")


@dataclass(frozen=True)
class EvidenceSignal:
    """One attributed signal offered in support of a declared obligation."""

    obligation_key: str
    source_role: str
    observed_at: datetime
    finality: str = "observed"
    closed: bool | None = None
    contradictory: bool = False

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None:
            raise ValueError("evidence observed_at must be timezone-aware")


@dataclass(frozen=True)
class ObligationResult:
    obligation: EvidenceObligation
    satisfied: bool
    fresh: bool | None
    contradictory: bool
    reason_code: str
    selected_source_role: str | None

    @property
    def key(self) -> str:
        return self.obligation.key

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "description": self.obligation.description,
            "required_source_roles": list(self.obligation.source_roles),
            "required_finalities": list(self.obligation.allowed_finalities),
            "max_age_seconds": self.obligation.max_age_seconds,
            "requires_closed": self.obligation.requires_closed,
            "satisfied": self.satisfied,
            "fresh": self.fresh,
            "contradictory": self.contradictory,
            "reason_code": self.reason_code,
            "selected_source_role": self.selected_source_role,
        }


@dataclass(frozen=True)
class ClaimAssessment:
    profile_id: str
    profile_version: int
    state: ClaimState
    completeness: Completeness
    freshness: Freshness
    contradiction: Contradiction
    denominator: int
    satisfied: int
    as_of: datetime
    obligations: tuple[ObligationResult, ...]

    @property
    def unmet_obligations(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.obligations if not item.satisfied)

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.reason_code for item in self.obligations))

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "state": self.state.value,
            "completeness": self.completeness.value,
            "freshness": self.freshness.value,
            "contradiction": self.contradiction.value,
            "denominator": self.denominator,
            "satisfied": self.satisfied,
            "as_of": self.as_of.isoformat(),
            "unmet_obligations": list(self.unmet_obligations),
            "reason_codes": list(self.reason_codes),
            "obligations": [item.as_dict() for item in self.obligations],
        }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("assessment as_of must be timezone-aware")
    return value.astimezone(timezone.utc)


def _obligation_failure(
    obligation: EvidenceObligation,
    reason_code: str,
    *,
    contradictory: bool = False,
) -> ObligationResult:
    return ObligationResult(
        obligation,
        False,
        None,
        contradictory,
        reason_code,
        None,
    )


def _signals_for_source_roles(
    obligation: EvidenceObligation,
    candidates: list[EvidenceSignal],
) -> list[EvidenceSignal]:
    return [item for item in candidates if item.source_role in obligation.source_roles]


def _signals_with_allowed_finality(
    obligation: EvidenceObligation,
    candidates: list[EvidenceSignal],
) -> list[EvidenceSignal]:
    if not obligation.allowed_finalities:
        return candidates
    return [item for item in candidates if item.finality in obligation.allowed_finalities]


def _signals_with_required_closure(
    obligation: EvidenceObligation,
    candidates: list[EvidenceSignal],
) -> list[EvidenceSignal]:
    if not obligation.requires_closed:
        return candidates
    return [item for item in candidates if item.closed is True]


def _newest_signal(candidates: list[EvidenceSignal]) -> EvidenceSignal:
    return max(
        candidates,
        key=lambda item: (item.observed_at.astimezone(timezone.utc), item.source_role),
    )


def _signal_is_fresh(
    obligation: EvidenceObligation,
    signal: EvidenceSignal,
    *,
    as_of: datetime,
) -> bool | None:
    if obligation.max_age_seconds is None:
        # Absence of an SLA is absence of a freshness claim.  It must not turn
        # an arbitrarily old observation into positive "fresh" evidence.
        return None
    age = (as_of - signal.observed_at.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= obligation.max_age_seconds


def _freshness_reason(fresh: bool | None) -> str:
    if fresh is True:
        return "satisfied"
    if fresh is False:
        return "required_evidence_stale"
    return "satisfied_freshness_not_declared"


def _candidate_result(
    obligation: EvidenceObligation,
    candidates: list[EvidenceSignal],
    *,
    as_of: datetime,
) -> ObligationResult:
    attributed = _signals_for_source_roles(obligation, candidates)
    if not attributed:
        reason = "source_role_mismatch" if candidates else "required_evidence_missing"
        return _obligation_failure(obligation, reason)

    if any(item.contradictory for item in attributed):
        return _obligation_failure(
            obligation,
            "required_evidence_contradictory",
            contradictory=True,
        )

    finalized = _signals_with_allowed_finality(obligation, attributed)
    if not finalized:
        return _obligation_failure(obligation, "required_finality_missing")

    closed = _signals_with_required_closure(obligation, finalized)
    if not closed:
        return _obligation_failure(obligation, "required_closure_missing")

    # Prefer the newest acceptable signal, with stable source-role tie-breaking.
    selected = _newest_signal(closed)
    fresh = _signal_is_fresh(obligation, selected, as_of=as_of)
    return ObligationResult(
        obligation,
        True,
        fresh,
        False,
        _freshness_reason(fresh),
        selected.source_role,
    )


def _unknown_assessment(
    profile: ClaimProfile,
    *,
    denominator: int,
    as_of: datetime,
) -> ClaimAssessment:
    return ClaimAssessment(
        profile.profile_id,
        profile.version,
        ClaimState.UNKNOWN,
        Completeness.UNKNOWN,
        Freshness.UNKNOWN,
        Contradiction.UNKNOWN,
        denominator,
        0,
        as_of,
        (),
    )


def _group_signals(
    signals: tuple[EvidenceSignal, ...] | list[EvidenceSignal],
) -> defaultdict[str, list[EvidenceSignal]]:
    grouped: defaultdict[str, list[EvidenceSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.obligation_key].append(signal)
    return grouped


def _completeness(*, satisfied: int, denominator: int) -> Completeness:
    if satisfied == denominator:
        return Completeness.COMPLETE
    return Completeness.PARTIAL


def _freshness(results: tuple[ObligationResult, ...], *, all_satisfied: bool) -> Freshness:
    if any(item.fresh is False for item in results):
        # A known stale signal remains stale even when another obligation is
        # missing. Do not collapse the independent axes into a single enum.
        return Freshness.STALE
    if all_satisfied and all(item.fresh is True for item in results):
        return Freshness.FRESH
    return Freshness.UNKNOWN


def _contradiction(
    results: tuple[ObligationResult, ...],
    *,
    all_satisfied: bool,
) -> Contradiction:
    if any(item.contradictory for item in results):
        return Contradiction.CONTRADICTORY
    if all_satisfied:
        return Contradiction.CLEAR
    return Contradiction.UNKNOWN


def _claim_state(
    completeness: Completeness,
    freshness: Freshness,
    contradiction: Contradiction,
) -> ClaimState:
    if contradiction is Contradiction.CONTRADICTORY:
        return ClaimState.CONTRADICTORY
    if completeness is Completeness.PARTIAL:
        return ClaimState.PARTIAL
    if freshness is Freshness.STALE:
        return ClaimState.STALE
    if freshness is Freshness.UNKNOWN or contradiction is Contradiction.UNKNOWN:
        return ClaimState.UNKNOWN
    return ClaimState.COMPLETE


def assess_claim(
    profile: ClaimProfile,
    signals: tuple[EvidenceSignal, ...] | list[EvidenceSignal],
    *,
    as_of: datetime,
    schema_supported: bool = True,
) -> ClaimAssessment:
    """Evaluate signals against a predeclared profile without inferred obligations."""

    assessment_time = _aware_utc(as_of)
    denominator = len(profile.obligations)
    if not schema_supported or denominator == 0:
        return _unknown_assessment(profile, denominator=denominator, as_of=assessment_time)

    grouped = _group_signals(signals)
    results = tuple(
        _candidate_result(obligation, grouped[obligation.key], as_of=assessment_time)
        for obligation in profile.obligations
    )
    satisfied = sum(item.satisfied for item in results)
    all_satisfied = satisfied == denominator
    completeness = _completeness(satisfied=satisfied, denominator=denominator)
    freshness = _freshness(results, all_satisfied=all_satisfied)
    contradiction = _contradiction(results, all_satisfied=all_satisfied)
    state = _claim_state(completeness, freshness, contradiction)

    return ClaimAssessment(
        profile.profile_id,
        profile.version,
        state,
        completeness,
        freshness,
        contradiction,
        denominator,
        satisfied,
        assessment_time,
        results,
    )


STRUCTURAL_V1: Final = ClaimProfile(
    "structural",
    1,
    (
        EvidenceObligation("run_identity", "Run identity was observed.", ("runtime", "otel")),
        EvidenceObligation("root_span", "A root span was observed.", ("runtime", "otel")),
        EvidenceObligation(
            "branch_closure",
            "Every declared branch closed or was explicitly abandoned.",
            ("runtime", "otel"),
            requires_closed=True,
        ),
    ),
)

ECONOMIC_ESTIMATE_V1: Final = ClaimProfile(
    "economic-estimate",
    1,
    (
        EvidenceObligation(
            "meter_fact",
            "A final meter fact was observed.",
            ("runtime", "gateway", "otel"),
            allowed_finalities=("final", "settled"),
        ),
        EvidenceObligation(
            "valuation",
            "A scoped estimate valuation was observed.",
            ("pricing_table", "gateway"),
            allowed_finalities=("provisional", "final", "settled"),
        ),
        EvidenceObligation(
            "economic_scope",
            "Currency and workload scope were joined.",
            ("reconciler",),
            requires_closed=True,
        ),
    ),
)

PROVIDER_BILLED_V1: Final = ClaimProfile(
    "provider-billed",
    1,
    (
        EvidenceObligation(
            "authenticated_settlement",
            "An authenticated provider settlement was observed.",
            ("provider_authenticated",),
            allowed_finalities=("settled",),
        ),
        EvidenceObligation(
            "billing_scope_join",
            "Provider account/window and run scope were joined.",
            ("reconciler",),
            allowed_finalities=("final", "settled"),
            requires_closed=True,
        ),
    ),
)

OUTCOME_V1: Final = ClaimProfile(
    "outcome",
    1,
    (
        EvidenceObligation(
            "outcome_identity",
            "The outcome is bound to the evaluated case/run.",
            ("ci", "deterministic_test", "human"),
            requires_closed=True,
        ),
        EvidenceObligation(
            "outcome_result",
            "A bounded outcome result was observed.",
            ("ci", "deterministic_test", "human"),
            allowed_finalities=("final", "settled"),
        ),
    ),
)

CI_V1: Final = ClaimProfile(
    "ci",
    1,
    (
        EvidenceObligation(
            "protected_head",
            "Evidence is bound to the protected workflow head.",
            ("protected_ci",),
            allowed_finalities=("final", "settled"),
        ),
        EvidenceObligation(
            "protected_policy",
            "The evaluated policy digest came from protected configuration.",
            ("protected_ci",),
            allowed_finalities=("final", "settled"),
        ),
        EvidenceObligation(
            "ci_outcome",
            "A bounded external outcome is bound to the same head.",
            ("protected_ci", "deterministic_test"),
            allowed_finalities=("final", "settled"),
            requires_closed=True,
        ),
    ),
)

BUILTIN_PROFILES: Final = {
    item.profile_id: item
    for item in (
        STRUCTURAL_V1,
        ECONOMIC_ESTIMATE_V1,
        PROVIDER_BILLED_V1,
        OUTCOME_V1,
        CI_V1,
    )
}
