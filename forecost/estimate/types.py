"""Estimator data contracts. No point field exists anywhere by design."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RepoSignals:
    file_count_bucket: str  # '0-50' | '51-500' | '501-5k' | '5k+'
    primary_language: str | None = None
    has_tests: bool = False


@dataclass(frozen=True)
class TaskContext:
    prompt_text: str  # in-memory only; never persisted (core-free ledger invariant)
    cwd: str
    agent: str = "claude-code"
    model: str | None = None
    session_uid: str | None = None
    permission_mode: str | None = None
    repo_signals: RepoSignals | None = None


@dataclass(frozen=True)
class EstimateRange:
    currency: str  # one EstimateRange per currency the caller cares about
    unit: str  # 'USD' | 'tokens' | 'quota_pct'
    p10: float
    p50: float
    p90: float
    n_samples: int
    method: str  # 'empirical_quantiles' | 'cold_start_prior'
    confidence: str  # 'low' | 'medium' | 'high'
    category: str
    caveats: tuple[str, ...] = field(default_factory=tuple)
    # No `point` field. Callers must render a range or nothing (BASEMENT.md L1).


class Estimator(Protocol):
    def estimate(self, task: TaskContext, currency: str) -> EstimateRange: ...
