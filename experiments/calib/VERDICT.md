# Calibration Experiment — Verdict

**Run:** 2026-07-12 · **Data:** 102 main Claude Code session files, 601 extracted
prompt-turns (337 subagent-joined), 12 task categories, 23-day window
(2026-06-19 → 2026-07-12), single user (n=1). Extractor: `extract.py`. Backtest:
`backtest.py`. Raw output: `verdict.json`.

**Method:** rolling-origin backtest, 40-turn burn-in, hierarchical empirical quantiles
(M1) with empirical-Bayes shrinkage toward global, vs. two baselines (B0 global
quantiles, B1 unconditioned per-category quantiles). Log-scale quantiles, expm1 back to
native units. This is a real run against real local data — not a simulation.

## G-A — Calibration gate (cost, duration, files)

| Target | Verdict | Coverage P90 | Width (P90/P50) | Skill vs B0 | Worst-cell cov | n |
|---|---|---|---|---|---|---|
| **Cost** | **MARGINAL** | 0.884 (in [0.85,0.95] ✓) | 8.55x (need ≤4x ✗) | +8.2% (need ≥15% ✗) | 0.823 (≥0.75 ✓) | 558 |
| **Duration** | **MARGINAL** | 0.884 (✓) | 10.66x (need ≤4x ✗) | **−7.4%** (worse than B0 ✗) | 0.818 (✓) | 558 |
| **Files** | **MARGINAL** | 0.851 (✓) | 9.63x (need ≤5x for G-R1 ✗) | 0.0% (✗) | 0.824 (✓) | 558 |

**Reading:** coverage is honest across the board (the P90 line holds roughly as often
as claimed) — the intervals are not miscalibrated, they are **wide**. None of the three
targets clears the width or skill bar for a PASS. Two findings correct prior-round
assumptions:
1. **Duration does NOT calibrate better than cost on this corpus** — M1 is actually
   *worse* than the naive global baseline (negative skill). round5-decisions §6 inferred
   duration would likely calibrate better (no cache-pricing noise); that inference is
   **falsified** by this run. Session durations on this machine include long idle gaps
   even after the 5h idle-cap, and category doesn't discriminate duration well.
2. **Files-touched width (9.63x) misses G-R1's 5x bar** despite files_touched having a
   much less extreme raw range than cost — categories don't separate files-touched
   distributions as cleanly as hoped either.

**Consequence per PLAN.md's pre-committed MARGINAL path:** ship the ledger, ingestion,
and `reconcile` now. Estimates for all three targets run in **shadow mode** — computed
and logged for every turn, never displayed to the user — until more data (more turns,
better features: prompt file-mentions, repo signals, k-NN on task embeddings per
round3-estimation §3.2) either tightens the bands or the monthly re-run shows
improvement. No dollar/time/files range ships in the v1 receipt.

## G-R2 — Success-table separation

**Verdict: INSUFFICIENT-DATA.** Zero weak-labeled failures across all 601 turns (520
ok, 81 ambiguous, 0 fail). Every category with n≥15 shows a 100% success rate under the
current weak-label rules (test-never-green OR tail-error-with-≥3-consecutive-failures).

This is not a bug — it is the outcome round5-risk §6.1 predicted by name: *"the
founder's corpus may be too healthy to learn failure from."* Confirmed, on real data.
The weak-label rules are too conservative to fire on a corpus this clean, or this
user's Claude Code usage genuinely fails rarely by these signals. Cannot distinguish
those two explanations without either (a) a corpus with more failures (the volunteer
extension), or (b) explicit `/forecost mark` data once it exists in production.
**Consequence:** no success-rate table ships anywhere, even in shadow mode, until
explicit marks accumulate. Round 3's original deferral is fully vindicated by measurement.

## G-R3 — Mid-run guard retrospective precision

**Verdict: PASS.** The simple rule (flag if ≥3 consecutive tool errors, or a tail error
with ≥2 total errors) flagged 12 of 601 turns (2.0% — well under the 10% ceiling), and
8 of those 12 (66.7%) were non-`ok` turns (precision ≥ 60% bar cleared).

**This is the strongest positive result of the experiment**, and it validates round5-risk's
central claim: mid-run detection of the present is easier than prediction of the future.
**Consequence:** the guard ships in Phase 1 as a shadow detector (log flags, don't
surface them) and is promoted to user-facing `ask` prompts in Phase 2 once more data
confirms precision holds at scale — per PLAN.md's G-R3 path, this already clears the bar,
so Phase 2's promotion is now empirically supported, not just hoped for.

## Honest limitations of this run

- **n=1 user.** A finding here proves existence (or, for duration, non-existence) for
  one real heavy user, not universality. The volunteer-corpus extension in G-A's
  INSUFFICIENT-DATA path is how universality gets tested.
- **23 days of history**, mostly one project family. Category cells like `refactor`
  (n=4) and `data-scripting` (n=1) never reach evaluable size.
- **Weak labels only** — no explicit `/forecost mark` data exists yet (that requires a
  shipped product). G-R2's null result is partly a labeling-conservatism artifact, not
  necessarily a true absence of failure.
- **Files-touched and duration targets are new** (added this round, not validated by
  Round 3's original protocol) — their pass/fail bars were set by round5-risk's
  proposal and have not been cross-checked against a second corpus.

## What this changes in the plan

1. **The v1 receipt ships with zero displayed prediction ranges.** Ledger + reconcile +
   outcomes capture + shadow estimator + shadow guard is the actual v1, not a
   simplification of it — this was already PLAN.md's MARGINAL path, now confirmed as
   the operative one rather than a hypothetical.
2. **The guard is real and should be built with more confidence than the plan assumed.**
   G-R3 passing on real data is the single most encouraging result here.
3. **Re-run monthly, and especially after production ingestion starts** (real installs
   accumulate cross-project, cross-user data the founder's own corpus cannot provide).
4. **Duration's negative skill is a genuine new open question**, not previously flagged:
   why does per-category conditioning hurt duration prediction here? Hypothesis: category
   correlates with cost/complexity but not clock time (a slow test-work turn and a fast
   test-work turn can have similar cost but very different wall time due to waiting/idle
   periods the 5h cap doesn't fully remove). Worth a dedicated look before Phase 2.
