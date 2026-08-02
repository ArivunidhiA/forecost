# Forecost audit 2 — product reality, refactor recovery, and 2026 direction

**Date:** 2026-08-02  
**Branch audited:** `fix/meter-correctness-audit-remediation` at `e4076b32`  
**Public main:** `f38c96a3`  
**Scope:** the last two months of locally accessible Forecost conversations, every local/remote
Git ref, PRs #1–#2, the current source and package, a clean-install journey, current primary
sources, and independent history, runtime/graph, security/trust, usability, and product-market
reviews.

This is a product and architecture audit. It intentionally does not implement the recommended
pivot before its core demand hypothesis is tested.

## Executive verdict

The user's instinct is correct: **Forecost is not yet a usable product.** It is a serious,
well-tested accounting substrate with a fragmented and partly inaccurate product surface.

The remembered July refactor is real. It was merged to `main` in PR #1, but only its
ledger-first foundation was implemented. The differentiated end-to-end loop was not:

```text
flight recorder
  -> brief at a real delegation/plan pause
  -> arm a resource envelope
  -> observe loops/fan-out while the run is live
  -> produce an independent receipt
  -> learn cost per successful outcome
```

The governing question was **“Can I walk away from this run?”** The current product mostly
answers **“What list-price-equivalent token spend did I ingest after the run?”** Those are not
the same job.

The ledger work should be preserved, but Forecost should not launch as another Claude usage
CLI, generic agent observability platform, or task-cost predictor. The product and runtime
reviews exposed a useful disagreement: the product-market lens favored an independent run
receipt/diff, while the graph/runtime lens favored concurrency-safe resource ownership. The
best sequence is:

> **First, give API-billed autonomous-agent teams one content-free run receipt that reconciles
> runtime/gateway/provider evidence and verified outcome. Then, only if operators demonstrate
> the need, let that same graph identity own an envelope that parallel branches and retries
> cannot double-spend.**

That recommendation is a deliberate update to the July thesis based on new evidence. It is
also a hypothesis, not permission to spend months rebuilding. A 14-day demand and cap-soundness
test comes first.

## 1. What was discussed, decided, and actually shipped

### Recovered conversation

The original redesign is in the local Claude archive, not primarily in Codex:

- The founder grants latitude to change the idea, market, name, and architecture in
  [`40978…jsonl`](</Users/ariv07/.claude/projects/-Users-ariv07-Desktop-forecost-update-forecost/40978a44-caf2-4158-83a9-68a5fcb87c1b.jsonl:51>).
- The research synthesis says “Kill the current product…” at
  [line 243](</Users/ariv07/.claude/projects/-Users-ariv07-Desktop-forecost-update-forecost/40978a44-caf2-4158-83a9-68a5fcb87c1b.jsonl:243>).
- The adversarial pass concludes “The basement is poured” at
  [line 405](</Users/ariv07/.claude/projects/-Users-ariv07-Desktop-forecost-update-forecost/40978a44-caf2-4158-83a9-68a5fcb87c1b.jsonl:405>).
- The founder requests every phase and end-to-end testing at
  [line 412](</Users/ariv07/.claude/projects/-Users-ariv07-Desktop-forecost-update-forecost/40978a44-caf2-4158-83a9-68a5fcb87c1b.jsonl:412>).
- The implementation response later acknowledges that only Phase 0/1 were built at
  [line 1354](</Users/ariv07/.claude/projects/-Users-ariv07-Desktop-forecost-update-forecost/40978a44-caf2-4158-83a9-68a5fcb87c1b.jsonl:1354>).

The authoritative strategy is in
[`BASEMENT.md`](</Users/ariv07/Desktop/FORECOST FINAL/forecost/.claude/research/repositioning/BASEMENT.md:28>),
[`PLAN.md`](</Users/ariv07/Desktop/FORECOST FINAL/forecost/.claude/research/repositioning/PLAN.md:1>),
[`DECISIONS.md`](</Users/ariv07/Desktop/FORECOST FINAL/forecost/.claude/research/repositioning/DECISIONS.md:7>),
and [`HANDOFF.md`](</Users/ariv07/Desktop/FORECOST FINAL/forecost/.claude/research/repositioning/HANDOFF.md:473>).
The accepted product was deliberately narrower than the proposed six-module “preflight
intelligence platform,” which the research explicitly rejected.

### Continuity failure

All four governing documents live under `.claude/`, are ignored by
[`.gitignore`](</Users/ariv07/Desktop/FORECOST FINAL/forecost/.gitignore:64>), and have never
been committed. The public repository retained ledger-centric prose and code, not the product
contract. Later audits therefore optimized the visible foundation as though it were the full
product.

### Timeline

| Date | Event | Reality |
|---|---|---|
| 2026-03-21 | PyPI/GitHub `v0.1.1` | The old calendar-spend forecasting product. |
| 2026-07-12 | Deep repositioning research | Old product rejected; flight-recorder/preflight/guard/receipt loop accepted. |
| 2026-07-12 | `e8de50be`, PR #1 | 5,700+ lines add the ledger, Claude ingestion, policy skeleton, shadow estimate, and plugin scaffolding. |
| 2026-07-12 | PR #1 merged to `main` | Refactor foundation reached GitHub, not PyPI. |
| 2026-07-17 | Correctness audit and fixes | Work correctly freezes expansion to repair meter correctness and trust. |
| 2026-08-02 | PR #2 at `e4076b32` | Major correctness/privacy/release hardening; open and unmerged, with green CI. |
| 2026-08-02 | Public distribution | PyPI is still `0.1.1`; public users cannot install the current product. |

No alternative full implementation is hiding on another local or remote branch.

## 2. Refactor contract versus implementation

| Accepted requirement | Status | Evidence / assessment |
|---|---|---|
| Kill calendar-spend forecasting as the product | **Not completed** | Ten legacy commands still share the default CLI in [`cli.py`](../forecost/cli.py); `demo` runs the dead product. |
| Local, independent, content-minimized ledger | **Substantially implemented on PR #2** | Atomic event/posting writes, idempotency, recovery, pricing provenance, bounded normalization, and owner-only storage are credible foundations. |
| Correct Claude Code ingestion | **Implemented on PR #2** | The latest branch repairs duplicate content-block accounting and pricing errors that previously compounded into materially false totals. |
| Claude plugin | **Partial** | Hooks exist, but not at `ExitPlanMode`; there is no statusline or post-run receipt. |
| LiteLLM integration | **Partial and unsafe as a hard gate** | It sync-writes SQLite in an async callback, can lose events on failure, and has no usable session scope or atomic reservation. |
| Cost, quota, time, files, and outcomes | **Mostly missing** | Cost/tokens exist. `plans`, `outcomes`, and `policy_decisions` are schema-shaped but have no production writers; graph duration/files/outcomes are absent. |
| Brief at plan approval/fan-out/delegation | **Missing** | [`hooks.json`](../plugin/hooks/hooks.json) binds generic prompt submission and selected tools, not `ExitPlanMode`; the output is task class + prompt regex + budget state. |
| Calibrated ranges, with error published | **Cost-only shadow path** | The cost estimator is honestly hidden; its calibration was marginal. Duration/files were not implemented. |
| Mid-run neutral guard | **Shadow-only and post-run** | It scans error booleans at `Stop`; the spend-without-progress detector is unwired. That is not live loop control. |
| One-action cap from the brief | **Missing** | Policy TOML, ledger budgets, burn, and estimates are disconnected abstractions. |
| Hard budget enforcement | **Promise contradicted** | Claude checks stale settled state before selected tools; current-turn usage arrives asynchronously at `Stop`. Concurrent LiteLLM calls can all pass together. |
| Independent provider books | **Missing** | [`reconcile_cmd.py`](../forecost/commands/reconcile_cmd.py) explicitly says Anthropic/OpenRouter provider reconciliation is not wired. |
| Receipt/statusline daily loop | **Missing** | No `StatusLine`/`PostToolUse` hooks and no user-facing receipt. |
| Cost-to-green / cost per accepted PR | **Missing** | Outcome schema exists; no production outcome capture or economics. |
| Cross-harness graph identity | **Missing** | Usage events have session/run labels but no trace/span/parent/link/attempt/branch/checkpoint lifecycle. |
| Free, local OSS; no hosted control plane | **Implemented** | This founder decision is consistently reflected. |
| Validate retention and adoption gates | **Not done** | There are no recorded design-partner outcomes, issues, or retention evidence. The repo currently has 1 star, 0 forks, and 0 issues. |

### Why the project feels unusable despite extensive code

1. **Foundation became the product.** The ledger was supposed to support every future path;
   that made it safe to build, but not sufficient to use.
2. **Architecture nouns replaced journeys.** Tables named `outcomes`, `plans`, and
   `policy_decisions` exist without an event-to-action-to-receipt path.
3. **Correctness debt consumed the roadmap.** The July handoff called the local core complete
   while showcasing totals later proven materially wrong. The next audit correctly prioritized
   trust, leaving the crown workflow untouched.
4. **The release never reached users.** PyPI still hosts the dead product. Current README
   instructions on the PR branch request `forecost==0.3.0`, which does not exist.
5. **The CLI has two products.** Current ledger commands, legacy forecasting, legacy HTTP/MCP,
   and optional extras appear as one system, but they read different databases and tell
   different stories.
6. **Self-calibration was mistaken for demand validation.** The 601-turn experiment measured
   feasibility on one corpus; it did not establish that strangers want the workflow.

## 3. Ranked audit

### P0 — release and thesis blockers

#### P0.1 — The documented install path is not a product

- PyPI only offers `0.1.1`, while the current README asks for `0.3.0`.
- Installing public `forecost` yields the legacy command set, and that package reports its CLI
  version as `0.1.0` despite PyPI serving `0.1.1`.
- `claude plugin marketplace add ArivunidhiA/forecost` fails because the marketplace manifest
  exists on the remediation branch but not on default `main`.
- The base wheel exposes `forecost-mcp`, but running it without the optional `mcp` dependency
  raises `ModuleNotFoundError`.
- The default demo initializes the legacy `costs.db` product.
- The Claude plugin is not part of an ordinary wheel install and requires a separate marketplace
  path that is not the README's five-minute journey.

**Required:** do not market or release 0.3 until one clean command produces the intended first
value from the exact artifact to be published.

#### P0.2 — “Hard budgets” are stale and raceable

- Claude `PreToolUse` checks only persisted state in
  [`handlers.py`](../forecost/hooks/handlers.py); ingestion happens asynchronously at
  `Stop`/`SessionEnd`.
- The matcher covers only `Task|Bash|WebFetch|WebSearch`.
- LiteLLM admission and settlement are separate read/write operations, without reservation.
- Missing LiteLLM session identity means session-scoped rules allow calls.

**Impact:** a long loop can overspend until it stops; N parallel branches can pass the same
remaining balance. This contradicts the central unattended-run promise.

An isolated lifecycle test made the timing concrete: prompt submission returned only
`task class 'fanout-batch'`; `PreToolUse` allowed the tool before `Stop`; `Stop` then ingested
USD 4.50; only the following `PreToolUse` denied a USD 1.00 cap. This is between-turn control,
not active-run control.

**Required:** either relabel the Claude lane as a settled-spend advisory or publish a tested
overrun bound. For gateways/runtimes, implement atomic idempotent reserve → commit/release with
expiry and parent/child ownership.

#### P0.3 — Economic authority is mislabeled

Claude subscriptions do not imply per-call dollar charges, yet transcript tokens become
“spend” at API list price and can trigger denial. LiteLLM `response_cost` is a gateway
calculation, not necessarily an invoice, but is preferred as a confident source.

**Required:** replace ambiguous bases with `billed`, `provider_estimate`, `gateway_estimate`,
`list_rate`, `contract_allocation`, `subscription_quota`, and `unknown`. Hard policies must
select which authorities are allowed.

#### P0.4 — “Independent reconciliation” is not independent

Current reconciliation recomputes stored events with Forecost's own pricing table or compares
two valuations already attached to the same local event. It cannot find a missing callback,
missing transcript, provider adjustment, or incomplete billing period.

**Required:** provider/admin cost adapters plus versioned reconciliation batches with source
watermarks, matched/unmatched counts, residual, tolerance, and freshness.

#### P0.5 — The data model cannot represent agent graphs

There is no trace/span/parent/link, operation kind, start/end/status, retry/attempt, branch,
handoff, checkpoint/resume, or fan-in identity. Forecost therefore cannot explain loop cost,
fan-out efficiency, branch ownership, retries, critical path, or durable resumes.

**Required:** define the content-free causal and economic event contract before adding adapters.
Use a compatible subset of OpenTelemetry GenAI and W3C Trace Context.

#### P0.6 — The actual product loop is absent

There is no real plan/delegation pause, cap-arming action, live guard, receipt, outcome mark,
or cost-per-success feedback. Until one loop exists, adding dashboards, model predictions, or
more commands increases surface area without increasing usefulness.

### P1 — high-priority architecture and trust gaps

1. **Gateway durability:** synchronous SQLite blocks LiteLLM's async path; callback failures
   are logged and lost. Use a tiny fsynced outbox and background settlement worker.
2. **Hot-path scaling:** canonical policy queries window-sort history per rule. Independent
   benchmarking measured roughly 82 ms at 40k postings, 523 ms at 250k, and 2.2 s at 1M before
   multiplying by rules. Maintain transactional scope/time-bucket counters.
3. **Two systems of record:** MCP and HTTP still read the deprecated database/forecaster while
   ledger commands read `ledger.db`. Remove or migrate them.
4. **Privacy contract disagreement:** raw workspace/transcript paths and some run/cursor values
   persist despite broader “content-free” language. Publish a field-level data inventory and
   pseudonymize all open-ended identifiers at one boundary.
5. **Tamper evidence:** ordinary owner-writable SQLite is not a flight recorder in the audit
   sense. Add chained digests and optional externally anchored checkpoints if “verifiable” is
   claimed.
6. **Generic meters:** four token counters cannot model reasoning, audio, images, web/code/MCP
   tool charges, service tier, cache class, batch discounts, or contracts. Separate immutable
   meter facts from valuations/charges.
7. **Money precision:** use integer micros or fixed decimals and preserve the exact tariff
   components used.
8. **Self-observability:** record ingestion freshness, source watermarks, queue depth,
   fail-open count, dropped/replayed events, policy decisions, and reconciliation coverage.
9. **Outcome validity:** do not revive cost-to-green until independent outcome labels and exact
   run identity exist.
10. **Contributor reproducibility:** official CI is green across Python 3.10–3.13, but the
    checked-in local virtual environment was moved from another checkout and its script
    shebangs are stale. Rebuild environments; never treat a copied `.venv` as evidence.

### P2 — opportunities after the P0/P1 loop works

- `runs list/show --json` with a content-free span DAG, branch/retry cost, wall time, critical
  path, and reconciliation freshness.
- LangGraph, OpenAI Agents SDK, AutoGen, Temporal, and OTel collectors via a versioned adapter
  capability contract.
- CI cost/outcome regression receipts once labels are credible.
- Optional signed, portable receipts and FOCUS-compatible cost export.
- A local viewer only after the CLI/SDK action loop demonstrates repeat use.

## 4. Current 2026 market evidence

The pain is real, but much of Forecost's July surface has been absorbed:

- The [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/usage/) automatically
  aggregates request/token usage across calls, tools, and handoffs and exposes per-request
  entries and hooks. Its [tracing](https://openai.github.io/openai-agents-python/tracing/)
  already models agent, generation, tool, guardrail, and handoff spans.
- [Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage) exports structured,
  redacted-by-default OTel metrics/events/traces. Its
  [hooks](https://code.claude.com/docs/en/hooks) include richer lifecycle surfaces, and agent
  teams make parallel execution a first-class workflow.
- [OpenTelemetry GenAI conventions](https://opentelemetry.io/blog/2026/genai-observability/)
  reduce the value of proprietary event schemas.
- [ccusage](https://github.com/ccusage/ccusage) already owns the zero-install, multi-harness
  coding-agent usage/statusline niche.
- [Langfuse cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
  and [agent graphs](https://langfuse.com/docs/observability/features/agent-graphs) cover generic
  observability, flexible usage units, and cyclic graph visualization.
- [AgentBudget](https://agentbudget.dev/docs) is a direct competitor with two-line Python/Go/TS
  cost enforcement, streaming, loop detection, finalization reserves, child budgets, and
  LangGraph/AutoGen adapters. “A ulimit for agents” is therefore not open positioning.
- [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview),
  [AutoGen termination](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html),
  and [Temporal](https://temporal.io/) already own orchestration, termination, and durable
  execution. Forecost should integrate with them, not become another runtime.

Two 2026 studies sharpen the opportunity:

1. [How Do AI Agents Spend Your Money?](https://arxiv.org/abs/2604.22750) reports agent tasks
   consuming roughly 1,000× more tokens than code chat/reasoning, up to 30× variation on the
   same task, no monotonic accuracy gain from more spend, and weak self-prediction correlation
   up to 0.39. This argues **against** task-cost prediction as the crown product.
2. [Token Budgets](https://arxiv.org/abs/2606.04056) catalogs 63 production overrun incidents
   and finds a simple counter sufficient for single agents but fan-out/delegation double-spend
   the differentiating failure class; its asyncio pattern overshot 30/30. This supports
   **resource ownership and concurrency soundness** as a real wedge.

### Assessment of the supplied repositories

| Repository | Use for Forecost? | Decision |
|---|---|---|
| [llm-council](https://github.com/karpathy/llm-council) | **Method, not dependency** | Reuse the blinded independent-opinion → peer-rank → synthesis pattern for product/audit research. Do not make multi-LLM councils a Forecost feature. |
| [Strix](https://github.com/usestrix/strix) | **Product pattern** | Learn from one-command onboarding, validated evidence rather than warnings, local run artifacts, and CI integration. Its security agent code is off-scope. |
| [caveman](https://github.com/JuliusBrussee/caveman) | **Benchmark scenario** | Use token-reduction skills as a real optimization experiment: does lower verbosity reduce resources without harming verified outcomes? Not a core dependency. |
| [Ruflo](https://github.com/ruvnet/ruflo) | **Integration stress case** | Its multi-agent/swarm graphs are useful for testing delegation, fan-out, retries, and resource ownership. Do not become a competing orchestrator. |
| [mattpocock/skills](https://github.com/mattpocock/skills) | **DX reference** | Study narrowly scoped, copyable skills and documentation. A Forecost install skill may follow only after the core SDK/CLI path works. |
| [claude-skills](https://github.com/alirezarezvani/claude-skills) | **Persona/workflow catalog** | Useful for discovering operator workflows and testing adapters; too broad to vendor into the product. Review individual licenses before reuse. |
| [obsidian-wiki](https://github.com/ar9av/obsidian-wiki) and [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) | **No core use** | Local ownership and plain-Markdown knowledge graphs are good documentation principles, but memory/PKM is outside Forecost's job. |
| [system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) | **Do not use** | Leaked prompts offer no durable product advantage and introduce provenance, policy, security, and maintenance risk. Use official APIs/hooks/OTel contracts instead. |

## 5. Twenty product lenses

These are modeled expert perspectives, not claims of employment at OpenAI or Anthropic.

| Lens | Conclusion |
|---|---|
| 1. Solo coding-agent user | Wants a zero-install glance; ccusage is already simpler. |
| 2. Unattended-agent operator | Needs a guarantee and stop reason, not a historical chart. |
| 3. AI startup founder | Cares when runaway work creates a surprise bill or blocks reliability. |
| 4. Platform engineer | Needs one policy across runtimes, retries, branches, and providers. |
| 5. FinOps buyer | Requires billed/list/allocated cost authority and reconciliation completeness. |
| 6. OpenAI-style runtime engineer | Would export trace/usage hooks; expects Forecost to consume, not reinvent them. |
| 7. Claude Code-style product engineer | Native hooks/OTel keep absorbing local telemetry; independent enforcement remains harder. |
| 8. Graph engineer | Parent/child ownership, fan-in links, attempts, and lifecycle are prerequisite data. |
| 9. Loop-safety engineer | Detecting repeated errors after Stop is not a live circuit breaker. |
| 10. Durable-execution engineer | Reservations need idempotency, leases, expiry, replay, and settlement semantics. |
| 11. Observability engineer | OTel-compatible facts are durable; proprietary dashboards are not a moat. |
| 12. Security engineer | Same-user hooks cannot be a strong security boundary; state the threat model. |
| 13. Privacy engineer | Content-minimized local data is valuable, but raw paths/IDs weaken the promise. |
| 14. Accounting engineer | Immutable meter facts and multiple valuation authorities matter more than a single “cost.” |
| 15. Data scientist | Preflight estimates are too stochastic and under-labeled to lead the product. |
| 16. Evaluation engineer | Cost is meaningful only beside independently measured outcome quality. |
| 17. Developer-experience lead | Five minutes to a prevented overrun or useful receipt is the adoption bar. |
| 18. OSS maintainer | A sharp primitive, benchmark, adapters, and composability attract stars; a mixed CLI does not. |
| 19. Skeptical investor | Ledger/UI is a feature; a provider-neutral resource-ownership protocol can become infrastructure. |
| 20. Future-resilience reviewer | Providers will absorb dashboards and counters faster than cross-provider semantics and independent proofs. |

## 6. Candidate directions

Scores are 1–5. They are judgment aids, not market proof.

| Direction | Pain | Frequency | Defensibility | Feasibility | Distribution | 3-year resilience | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Graph-aware run receipt: local/gateway/provider diff + outcome** | 5 | 4 | 4 | 3 | 4 | 5 | **25** |
| Concurrency-safe graph resource ownership/reservations | 5 | 3 | 4 | 2 | 3 | 5 | **22** |
| Cost/outcome regression receipts in CI | 4 | 4 | 3 | 2 | 4 | 4 | **21** |
| Coding-agent ledger/statusline | 2 | 5 | 1 | 5 | 5 | 2 | **20** |
| Generic agent observability/graph UI | 4 | 5 | 1 | 2 | 2 | 2 | **16** |
| Preflight task-cost prediction | 3 | 4 | 2 | 1 | 3 | 2 | **15** |

### Recommended vision

Forecost should remain an **independent economic evidence layer**, not an orchestrator:

```text
agent runtime / graph
  -> causal spans and immutable meter facts
  -> local vs gateway/OTel vs provider-bill reconciliation
  -> verified outcome + one verifiable run receipt
  -> optional atomic parent/child envelope after the control need is validated
```

The first artifact is `forecost receipt <run>` for API-billed autonomous-agent teams: what the
runtime observed, what the gateway valued, what the provider billed, what branches/retries
consumed, whether the run achieved its verified outcome, and where evidence disagrees. This is
more defensible than a Claude statusline and more immediately reachable from the existing ledger.

If control demand clears its gate, the envelope should support dollars, tokens, LLM calls, paid
tool calls, wall time, steps, retries, and concurrency. The differentiator from AgentBudget must
be proven, not asserted: **cross-process/distributed, graph-aware ownership with atomic reserve/
transfer/commit/release and durable replay semantics**, backed by the independent receipt.

### What to keep

- Atomic/idempotent ledger writer and append-oriented event/posting design.
- Content-minimization boundary and privacy canaries, strengthened to include identifiers/paths.
- Recovery spool and fail-open interactive philosophy.
- Versioned pricing and multiple valuation concept.
- CLI query layer and the best correctness tests.

### What to cut or quarantine

- Legacy forecast/init/demo/watch/serve/MCP from the default executable and base install.
- “Actual cost,” “hard cap,” and “independent books” claims until they are literally true.
- Shadow task-cost prediction as a launch feature.
- Generic prompt regex “preflight” as a product surface.
- Dashboard work and broad adapter count before the causal contract exists.
- The rejected six-module preflight intelligence platform.

## 7. Fourteen-day validation before a major rebuild

### Prototype

Build only a thin receipt vertical slice for **one runtime with real graph identity** (OpenAI
Agents SDK or LangGraph), one gateway/OTel source, and one provider cost source:

1. normalize the trace/span DAG and immutable meter facts;
2. reconcile local/runtime, gateway, and provider period/run evidence;
3. attach one independent `good|bad|partial` or test/PR outcome;
4. show unmatched events, residual, evidence authority, and freshness;
5. emit one content-free JSON/text receipt.

In a separate bounded technical spike—not a second product—test whether atomic parent/child
reservations close a real gap left by AgentBudget. Implement only enough reserve/commit/release
behavior to run the adversarial fan-out/retry benchmark.

Do not build a UI, prediction model, ten adapters, or hosted service.

### Demand work

- Interview 12 maintainers/operators who currently run parallel or unattended agent workflows.
- Ask for a real overrun/retry/fan-out incident and current workaround; do not pitch first.
- Recruit 5 design partners from framework issues/discussions and agent infrastructure teams.
- Show both concepts—independent run receipt and sound graph envelope—without asking leading
  questions. Record which artifact the operator would install this week.
- Compare directly with AgentBudget: if its two-line integration already solves the control job,
  do not build a competing budget SDK.

### Technical proof

- 100 concurrent child allocations cannot exceed the parent envelope.
- retries/replays do not double-charge.
- crash between reserve and settlement recovers deterministically.
- expired leases return capacity safely.
- overhead remains bounded independently of historical ledger size.
- receipt reports complete/incomplete evidence and reconciles source totals reproducibly.

### Continue criteria

Continue only if, within 14 days:

- at least 5 qualified operators install the prototype;
- at least 3 generate a receipt from their own real graph;
- at least 2 find an actionable discrepancy or change a run/model/workflow decision;
- build the envelope only if at least 3 report a recurring overrun/control problem not already
  solved acceptably and cap-soundness shows zero declared envelope violations; and
- at least 3 users choose to keep it enabled for a second week.

Kill the receipt direction if fewer than 3 qualified teams will connect two independent sources
or no one acts on a discrepancy. Kill the governor direction if fewer than 3 teams can produce a
painful recurring incident, AgentBudget/native runtime controls solve the job without a material
gap, or the only interest is in dashboards and star-gazing.

## 8. Implementation checklist after validation

### Batch A — truth and product contract

- [ ] Commit a privacy-safe ADR containing identity, user job, product laws, settled rejections,
      threat model, economic-authority vocabulary, and requirement/status matrix.
- [ ] Make the public README truthful about what ships today.
- [ ] Remove the nonexistent PyPI version from docs until the artifact is published.
- [ ] Quarantine legacy commands and move legacy MCP/HTTP behind an explicit extra/executable.
- [ ] Define one five-minute golden path and test the exact release wheel/plugin artifact.
- [ ] Add `forecost setup claude --session-cap-usd N` plus an end-to-end hook self-test.
- [ ] Make `doctor` report whether the plugin is installed, hooks have executed successfully,
      transcript discovery is fresh, and protection is inactive rather than failing silently.

### Batch B — causal/economic foundation

- [ ] Define `conversation/trace/span/link/attempt/lifecycle` identities compatible with OTel.
- [ ] Add immutable generic meter facts and fixed-precision valuations/charges.
- [ ] Add explicit economic authority and account mode.
- [ ] Add source watermarks and versioned reconciliation batches.
- [ ] Normalize/pseudonymize every persistent open-ended identifier through one boundary.

### Batch C — one complete receipt loop

- [ ] Integrate one graph runtime end to end.
- [ ] Integrate one independent gateway/OTel source and one provider cost source.
- [ ] Produce a content-free receipt with graph, economic authority, discrepancy, evidence
      freshness, verified outcome, and reconciliation status.
- [ ] Capture explicit `good|bad|partial` plus independent test/PR signals.
- [ ] Add `runs list/show --json` before any graphical dashboard.

### Batch D — sound resource envelopes, only after the control gate

- [ ] Implement atomic parent/child reservations, transfers, commit/release, TTL, and recovery.
- [ ] Unify policy TOML, burn, budgets, and receipt around one budget compiler.
- [ ] Maintain O(1) settled/reserved counters for the hot path.
- [ ] Add a durable outbox for gateway telemetry.
- [ ] Show the envelope at a real plan/delegation boundary where available.
- [ ] Emit a live neutral loop/runaway fact with an explicit action.
- [ ] Publish the enforcement boundary and maximum possible overrun per adapter.

### Batch E — trust and release

- [ ] Provider/admin reconciliation for at least one OpenAI and one Anthropic-compatible lane.
- [ ] Tamper-evident sequence/checkpoints if “flight recorder” or “verifiable” remains in copy.
- [ ] Structured `doctor --json` with freshness, queue, fail-open, replay, and coverage health.
- [ ] Rebuild artifacts from a clean checkout; generate SBOM/provenance; install-test all extras.
- [ ] Publish the package and plugin before announcing the quickstart.

### Batch F — distribution after repeated use

- [ ] Publish the concurrency/overrun benchmark and reproducible failure corpus.
- [ ] Create focused adapters for OpenAI Agents SDK, LangGraph, LiteLLM, then Claude OTel/hooks.
- [ ] Provide copy-paste examples in real agent repositories.
- [ ] Write migration guides from counters/AgentBudget only where Forecost has a demonstrated gap.
- [ ] Track activation, second-run rate, weekly retained projects, prevented overruns, reconciliation
      coverage, and receipt views—not stars as the primary product metric.

## 9. Verification performed

- Git history, all local/remote branches, PR #1, PR #2, and current GitHub checks inspected.
- Relevant local Codex and Claude archives for June–August searched; the original Claude session
  and July Codex audit were recovered. Inaccessible cloud-only history is not claimed as searched.
- Clean package smoke test installed local source and exercised doctor, ingest, ledger, reconcile,
  burn, calibration, demo, and MCP entry points.
- Core tests: **362 passed** when benchmarks were excluded from the stale local virtualenv.
- Full local virtualenv run: **371 passed, 2 setup errors** because `pytest-benchmark` was absent.
- Ruff on `forecost/ tests/`: passed.
- Pyright through the virtualenv's interpreter: 0 errors.
- Current GitHub CI: all lint, security, coverage, smoke, and Python 3.10–3.13 OS-matrix checks pass.
- Independent security review found no credible committed secrets; fresh dependency audit found no
  known vulnerabilities. The highest trust risks are semantic overclaims and enforcement races,
  not a conventional dependency vulnerability.

## Final call

Do not discard Forecost's ledger. Do not confuse it with the product either.

The July pivot was directionally right but incomplete, and its private contract was allowed to
disappear from the repository's memory. The next move is not another broad refactor. It is a
two-week falsifiable test of one sharper artifact: **an independent, graph-aware economic receipt
for a real autonomous-agent run.** That receipt establishes the identity/evidence substrate;
sound parent/child resource ownership is the next product only if operators prove native controls
and AgentBudget leave a material gap. If users do not pull either primitive into real workflows,
stop before building another impressive foundation without a user loop.
