# Forecost master checklist — production product plan

**Prepared:** 2026-08-02  
**Planning basis:** `docs/audit-2.md`, current branch `e4076b32`, local history, cold-start
testing, and final modeled OpenAI-runtime and Anthropic-coding-agent reviews.  
**Status:** plan only. No feature implementation is authorized by this document.

## Ownership legend

- **[CODEX]** — can be designed, implemented, tested, documented, and release-prepared locally
  without founder labor, credentials, production data, or third-party connections.
- **[FOUNDER]** — a product, privacy, branding, risk, or publication decision that should remain
  with the project owner. A recommended default is included.
- **[FIELD]** — requires real operators, real provider/account data, an external marketplace, or
  another party. Synthetic/offline support can still be built by Codex first.

## Product north star

**Recommended first product:**

> Forecost produces an independent, content-free, graph-aware economic receipt for an
> autonomous-agent run: what the runtime observed, what each meter valued, what the provider
> billed, which branches/retries consumed resources, whether the outcome was verified, and where
> the evidence disagrees.

**Conditional second product:**

> When field evidence shows that native controls and AgentBudget are insufficient, Forecost lets
> a graph own a resource envelope that parallel branches, retries, crashes, and resumes cannot
> double-spend.

The receipt and envelope share one causal/economic kernel. Forecost remains an independent
evidence/control layer; it does not become an agent orchestrator, generic observability UI, or
prediction platform.

## Non-goals and cuts

- [ ] **[CODEX]** Remove task-cost forecasting from hero positioning; retain the existing
      estimator only as clearly labeled research/shadow code until its retention value is proven.
- [ ] **[CODEX]** Do not build the rejected six-module “preflight intelligence platform.”
- [ ] **[CODEX]** Do not build a hosted dashboard/control plane before local repeat use exists.
- [ ] **[CODEX]** Do not build a generic agent graph viewer; emit portable JSON/text/Markdown
      receipts and integrate with existing observability tools.
- [ ] **[CODEX]** Do not add ten shallow adapters before the causal identity and adapter
      conformance contracts are frozen.
- [ ] **[CODEX]** Do not claim safety, hard enforcement, actual cost, provider reconciliation,
      or “safe to walk away” where the evidence/capability does not support it.
- [ ] **[CODEX]** Do not make model-routing recommendations from observational spend data.
- [ ] **[CODEX]** Do not use leaked system prompts as product data or dependencies.
- [ ] **[FOUNDER]** Do not optimize the roadmap for GitHub stars alone. Stars are a distribution
      result; activation, second-run use, actionable discrepancies, and prevented overruns are
      product evidence.

---

# Part I — autonomous Codex work

Everything below can be completed locally with synthetic fixtures and deterministic tests once
implementation is authorized.

## A0 — Put the real product contract under version control

- [ ] **A0.1 [CODEX] P0** Create a tracked `docs/product-contract.md` distilled from the private
      July corpus: customer, job, identity, product laws, threat model, economic vocabulary,
      supported claims, non-goals, and evidence gates.
- [ ] **A0.2 [CODEX] P0** Add a requirement/status matrix linking every product promise to its
      writer, reader, user surface, tests, and release state.
- [ ] **A0.3 [CODEX] P0** Add ADRs for graph identity, meter/charge separation, economic authority,
      receipt versioning, resource ownership, privacy identifiers, and legacy retirement.
- [ ] **A0.4 [CODEX] P0** Make `docs/status.md` generated or release-checked so it cannot contradict
      README, package metadata, plugin metadata, changelog, or code capability.
- [ ] **A0.5 [CODEX] P1** Add a decision log template so future research cannot disappear into
      ignored `.claude/`/`.codex/` state.

**Acceptance gate A0**

- [ ] A contributor can identify the target user, supported promise, data boundary, current
      product state, and next gate without reading private chat history.
- [ ] CI detects a capability marked “shipped” when its end-to-end test or public artifact is
      absent.

## A1 — Make the repository one truthful product

- [ ] **A1.1 [CODEX] P0** Move `forecast`, `init`, `demo`, `serve`, `track`, `watch`, `optimize`,
      and other dead-product commands under `forecost legacy ...` or a separate optional
      executable with an explicit removal date.
- [ ] **A1.2 [CODEX] P0** Migrate MCP and any retained HTTP reads to the canonical ledger/query
      service; never expose legacy `costs.db` as current Forecost data.
- [ ] **A1.3 [CODEX] P0** Stop exposing `forecost-mcp` from the base wheel unless its dependency is
      installed; provide a clear optional-extra diagnostic instead of a traceback.
- [ ] **A1.4 [CODEX] P0** Establish one version source for package, CLI, plugin, marketplace,
      changelog, Git tag, and built artifact.
- [ ] **A1.5 [CODEX] P0** Rewrite public claims using precise terms: `token usage`, `list-rate
      equivalent`, `gateway estimate`, `provider billed`, `subscription quota`, and
      `reconciliation coverage`.
- [ ] **A1.6 [CODEX] P0** Add a machine-readable capability matrix by adapter: identity, graph,
      live usage, billing authority, enforcement boundary, finality, and maximum overrun.
- [ ] **A1.7 [CODEX] P1** Remove or redesign the unauthenticated loopback server. If retained,
      require owner-only IPC or a random bearer token plus Host/Origin validation.
- [ ] **A1.8 [CODEX] P1** Remove `init --smart` from the supported product or rebuild it with an
      exact outbound manifest, secret redaction, untrusted-data delimiting, and strict response
      validation.

**Acceptance gate A1**

- [ ] `forecost --help`, README, plugin README, PyPI-ready metadata, and `doctor` describe the
      same product and capabilities.
- [ ] A base-wheel install has no broken entry point and imports no legacy forecasting stack on
      the current path.
- [ ] No current command reads or writes the wrong database.

## A2 — Freeze the causal and economic kernel before adding adapters

- [ ] **A2.1 [CODEX] P0** Define typed, versioned identities: `conversation_id`, `trace_id`,
      `run_id`, `span_id`, `parent_span_id`, span links for fan-in, source sequence, and stable
      idempotency key.
- [ ] **A2.2 [CODEX] P0** Define lifecycle: `created`, `queued`, `running`, `waiting`, `completed`,
      `failed`, `cancelled`, `incomplete`, `replayed`, and `superseded`.
- [ ] **A2.3 [CODEX] P0** Define operation kinds: agent, model, tool, handoff, guardrail, checkpoint,
      human approval, queue/wait, and custom.
- [ ] **A2.4 [CODEX] P0** Model attempt/retry-of, branch, checkpoint/resume, durable replay, agent
      identity, and workflow/node identity without storing prompts or tool payloads.
- [ ] **A2.4A [CODEX] P0** Introduce a versioned append-only observation journal: producer,
      source sequence, idempotency key, event kind, occurred/observed times, causal envelope,
      typed payload, and superseded observation. Treat query tables as rebuildable projections.
- [ ] **A2.4B [CODEX] P0** Define deterministic projection ordering from causal/source identity and
      stable keys—never SQLite row ID or arrival order.
- [ ] **A2.5 [CODEX] P0** Add immutable generic `meter_facts`: unit, fixed-precision quantity,
      dimensions, source, observed time, finality, and span identity.
- [ ] **A2.5A [CODEX] P0** Encode aggregation semantics (`delta`, `subset`, `checkpoint`, `gauge`)
      so generation, turn, task, and run totals cannot be summed accidentally.
- [ ] **A2.6 [CODEX] P0** Add immutable `charges/valuations`: fixed-precision amount, currency,
      authority, line item, exact tariff/rate components, account scope, billing period, and
      supersession link.
- [ ] **A2.7 [CODEX] P0** Replace SQLite/Python floating money with integer micros or decimal
      strings and documented rounding rules.
- [ ] **A2.8 [CODEX] P0** Add explicit authority values: billed, provider estimate, gateway
      estimate, list rate, contract allocation, subscription quota, and unknown.
- [ ] **A2.9 [CODEX] P0** Define outcome evidence: explicit mark, test result, build result, local
      commit/merge/revert fact, evidence source, confidence tier, observed time, and supersession.
- [ ] **A2.10 [CODEX] P0** Define a versioned receipt schema with completeness, provenance,
      discrepancy, outcome, stop reason, and integrity fields.
- [ ] **A2.11 [CODEX] P0** Implement forward-only schema migration with backup/dry-run,
      idempotency, rollback-on-failure, and old-ledger compatibility tests.
- [ ] **A2.12 [CODEX] P1** Align the schema with a content-free subset of OTel GenAI and W3C Trace
      Context while retaining Forecost-specific economic fields.
- [ ] **A2.13 [CODEX] P1** Validate conforming W3C trace/span identifiers, deterministically
      crosswalk nonconforming source IDs, never persist baggage, and omit tracestate by default.

**Acceptance gate A2**

- [ ] The schema represents fan-out, fan-in, retries, handoffs, checkpoints, waits, failures,
      durable resumes, tool charges, token usage, provider bills, and verified outcomes.
- [ ] Canonical JSON serialization is deterministic and versioned.
- [ ] Unknown/future fields fail safely or round-trip according to an explicit compatibility rule.
- [ ] No free-form external string reaches persistent state without validation or irreversible
      normalization.

## A3 — Build an offline “Run Lab” and conformance corpus

- [ ] **A3.1 [CODEX] P0** Add a synthetic, content-free corpus covering single calls, tools,
      handoffs, fan-out/fan-in, nested agents, loops, retries, late events, streaming finality,
      cancellations, crashes, and resumes.
- [ ] **A3.2 [CODEX] P0** Add synthetic local/runtime, gateway, OTel, provider-bill, subscription,
      and quota views of the same runs, including deliberate missing and contradictory facts.
- [ ] **A3.3 [CODEX] P0** Add `forecost lab demo` to create an isolated ledger and render the new
      product without reading a user's home directory.
- [ ] **A3.4 [CODEX] P0** Add `forecost lab chaos` to generate deterministic concurrent graph
      histories with seed-based replay.
- [ ] **A3.5 [CODEX] P0** Add crash points before/after reserve, outbox append, ledger commit,
      settlement, receipt finalization, and checkpoint anchoring.
- [ ] **A3.6 [CODEX] P1** Publish the corpus as the adapter conformance kit and product demo data.
- [ ] **A3.7 [CODEX] P1** Add a privacy sentinel to prompts, tool inputs/outputs, paths, IDs, error
      messages, recovery files, and imports; prove it never appears in persistent Forecost state.
- [ ] **A3.8 [CODEX] P0** Add a deterministic Claude lifecycle scenario covering SessionStart,
      prompt submission, plan exit, foreground/background agents, tool batches, failures, stop,
      interrupt, missing SessionEnd, and next-launch crash closure through the packaged launcher.

**Acceptance gate A3**

- [ ] Every critical behavior is reproducible offline from one seed.
- [ ] The lab never touches real transcripts, credentials, config, or `~/.forecost`.
- [ ] The same corpus drives unit, property, integration, performance, and documentation tests.

## A4 — Ship the first complete product loop: graph-aware run receipts

- [ ] **A4.1 [CODEX] P0** Add `forecost runs list` with status, duration, source coverage,
      reconciliation state, outcome state, and economic-authority summary.
- [ ] **A4.2 [CODEX] P0** Add `forecost runs show <run>` with a compact content-free causal tree/DAG,
      branch/retry cost, wall time, service time, wait time, fan-out width, and critical path.
- [ ] **A4.3 [CODEX] P0** Add `forecost receipt <run>` with stable text and JSON output.
- [ ] **A4.4 [CODEX] P0** Add `forecost receipt --markdown` for a local PR/CI artifact without any
      GitHub connection.
- [ ] **A4.5 [CODEX] P0** Add an evidence-completeness section: sources expected/present, source
      freshness, watermarks, final/provisional state, and known blind spots. Never turn it into a
      safety score.
- [ ] **A4.5A [CODEX] P0** Give receipts explicit evidence states: `complete`, `incomplete`,
      `conflicted`, or `unknown`; live lifecycle state remains separate.
- [ ] **A4.6 [CODEX] P0** Add `forecost mark <run> good|bad|partial` with optional structured,
      content-free reason codes.
- [ ] **A4.7 [CODEX] P0** Auto-capture local test/build exit status and Git commit/revert facts as
      separate evidence, never as infallible “success.”
- [ ] **A4.8 [CODEX] P1** Add `forecost receipt diff <run-a> <run-b>` for branch/retry/resource/
      outcome deltas.
- [ ] **A4.9 [CODEX] P1 — novel** Compute an **Economic Trace Fingerprint**: a privacy-safe hash of
      graph structure, operation kinds, model classes, meter dimensions, and outcome tier. Use it
      to compare repeated strategies without prompts or repository content.
- [ ] **A4.10 [CODEX] P1 — novel** Add counterfactual revaluation against an alternate pricing
      snapshot or contract file, clearly labeled as a revaluation—not a prediction.
- [ ] **A4.11 [CODEX] P1 — novel** Produce a **Resource Proof Receipt** containing graph totals,
      source completeness, reconciliation residual, outcome evidence, integrity head, and—when
      enabled—the budget conservation equation.
- [ ] **A4.11A [CODEX] P1 — novel** Canonicalize receipt bytes and compute a deterministic
      Merkle/evidence root so shuffled, delayed, or replayed observations produce the same receipt
      when the underlying evidence set is identical.
- [ ] **A4.12 [CODEX] P1** Add `--no-color`, narrow-terminal, deterministic timestamp, and accessible
      plain-language modes; preserve semantic exit codes and JSON stability.

**Acceptance gate A4**

- [ ] A fresh user reaches a meaningful synthetic receipt in under 60 seconds and three commands.
- [ ] A real-history user reaches their latest receipt without editing config.
- [ ] Text, JSON, and Markdown agree exactly on totals, authority, finality, and outcome.
- [ ] A receipt never says “actual,” “verified,” or “complete” without the supporting authority
      and evidence fields.
- [ ] Migration from the current schema preserves every existing event/posting and labels legacy
      evidence limitations explainably.

## A5 — Make reconciliation genuinely independent

- [ ] **A5.1 [CODEX] P0** Add versioned `reconciliation_batches` with source pair/set, account/project
      scope, dimensions, time window, watermarks, expected/observed totals, unmatched counts,
      residual, tolerance, freshness, provisional/final state, and supersession.
- [ ] **A5.2 [CODEX] P0** Reconcile both event-level matches and aggregate billing constraints so
      missing local events can be detected.
- [ ] **A5.3 [CODEX] P0** Preserve unmatched/ambiguous evidence instead of forcing a match.
- [ ] **A5.4 [CODEX] P0** Add offline file importers for representative OpenAI Costs/Usage and
      Anthropic Usage/Cost export shapes using synthetic fixtures; live HTTP is deferred.
- [ ] **A5.5 [CODEX] P0** Add gateway/OTel import fixtures and reconcile local → gateway/OTel →
      provider bill as three distinct authorities.
- [ ] **A5.6 [CODEX] P1** Add provisional/final/superseded reconciliation so late events reopen a
      receipt safely.
- [ ] **A5.7 [CODEX] P1** Add a tariff audit that can reproduce every historical valuation from
      stored rate components and record corrections as superseding charges.
- [ ] **A5.8 [CODEX] P1 — novel** Add a **Meter Disagreement Explainer** that classifies residuals
      using facts only: missing local event, late source, price authority difference, service
      tier, cache class, batch/discount, tool charge, rounding, or unknown.

**Acceptance gate A5**

- [ ] Synthetic missing callbacks/transcripts and provider adjustments are detected.
- [ ] Reconciliation is reproducible after pricing code changes.
- [ ] One local event with competing valuations is never double-counted.
- [ ] Incomplete source coverage is visible and cannot produce a “reconciled” claim.

## A6 — Prove graph-wide resource ownership offline

- [ ] **A6.1 [CODEX] P0** Replace disconnected policy/budget/trajectory concepts with one typed
      budget registry and compiler.
- [ ] **A6.2 [CODEX] P0** Support resource dimensions: money by authority, tokens, LLM calls,
      paid-tool units, wall time, steps, retries, and concurrency.
- [ ] **A6.3 [CODEX] P0** Add atomic reservation records: parent scope, child scope, requested and
      granted resources, idempotency key, lease/TTL, state, and provenance.
- [ ] **A6.4 [CODEX] P0** Implement `reserve`, `transfer/split`, `commit/settle`, `release/return`,
      `expire`, and `recover` under transactional local cross-process concurrency.
- [ ] **A6.5 [CODEX] P0** Enforce the conservation invariant:
      `parent capacity = settled + live reservations + returned capacity + explicit adjustment`.
- [ ] **A6.6 [CODEX] P0** Make retries/replays reuse stable reservation identity and never
      double-charge.
- [ ] **A6.7 [CODEX] P0** Maintain O(1) settled/reserved scope counters so admission cost is
      independent of ledger history.
- [ ] **A6.8 [CODEX] P0** Separate shadow, warn, ask, deny, and CI fail-closed modes. Interactive
      internal failures remain fail-open and visibly recorded.
- [ ] **A6.9 [CODEX] P1** Add finalization reserve, per-branch child caps, retry budgets, concurrency
      ceilings, and explicit stop reasons.
- [ ] **A6.10 [CODEX] P1** Add structural loop facts: repeated operation signature, error streak,
      retry count, spend/tokens since verified progress, and branch explosion. No predicted
      “failure probability.”
- [ ] **A6.11 [CODEX] P1 — novel** Add a **Budget Shadow Replay**: apply a proposed policy to a
      historical graph and report where it would have warned/stopped, with outcome evidence, but
      without causal savings claims.
- [ ] **A6.12 [CODEX] P1 — novel** Add a machine-verifiable **Cap Soundness Certificate** generated
      by the chaos suite: seed, policy, threat boundary, maximum declared overrun, conservation
      checks, and result.
- [ ] **A6.13 [CODEX] P1 — novel** Add a receipt-carried **linearizability witness**: reservation
      transition order, fencing token, invariant result, and evidence digest proving what the
      single-host ledger observed about parallel ownership.

**Acceptance gate A6**

- [ ] 100+ concurrent children cannot allocate beyond the parent envelope.
- [ ] Repeated idempotency keys, crashes, late settlements, expired leases, process restarts,
      branch joins, and durable replay preserve conservation.
- [ ] The declared threat model and maximum adapter overrun are printed beside every “deny/hard”
      claim.
- [ ] A simple counter/AgentBudget baseline is benchmarked honestly; Forecost proceeds only where
      its graph/distributed guarantees are materially different.

## A7 — Turn adapters into a tested protocol, not one-off parsers

- [ ] **A7.1 [CODEX] P0** Define an adapter capability contract: pull/push, event identity,
      lifecycle/finality, graph identity, meter dimensions, economic authority, watermarks,
      enforcement point, and privacy guarantees.
- [ ] **A7.2 [CODEX] P0** Add an adapter conformance test harness and CLI report.
- [ ] **A7.3 [CODEX] P0** Upgrade Claude JSONL ingestion to preserve available subagent/parent,
      lifecycle, tool, and source-sequence facts without content.
- [ ] **A7.4 [CODEX] P0** Replace LiteLLM synchronous callback SQLite work with a bounded, fsynced
      append-only outbox and background batch writer.
- [ ] **A7.5 [CODEX] P0** Add durable callback idempotency, poison-record handling, queue depth/age,
      replay count, and explicit drop/fail-open telemetry.
- [ ] **A7.6 [CODEX] P1** Add a file/stdin OTel receiver for content-free GenAI spans and metrics;
      no collector/network connection is required.
- [ ] **A7.7 [CODEX] P1** Add an optional OpenAI Agents SDK trace/usage adapter tested entirely
      against local fake runs and exported fixtures.
- [ ] **A7.7A [CODEX] P1** Document and test the OpenAI mapping: group/conversation, trace/workflow,
      one runner invocation/run, task/turn/agent/generation/tool/guardrail/handoff spans, and
      generation-level versus aggregate usage semantics. Select safe fields from typed span
      objects; never serialize full content-bearing spans and redact afterward.
- [ ] **A7.8 [CODEX] P1** Add a LangGraph callback/checkpoint adapter tested against local fake
      graphs, interrupts, replay, and parallel super-steps.
- [ ] **A7.9 [CODEX] P2** Add AutoGen termination/team and Temporal checkpoint/replay adapters only
      after the first two conformance paths are stable.
- [ ] **A7.10 [CODEX] P1** Publish a compatibility matrix and golden fixture for every adapter.

**Acceptance gate A7**

- [ ] Every adapter passes identity, duplicate, late-event, privacy, finality, crash, and receipt
      conformance tests.
- [ ] Adding an adapter requires no schema invention and cannot silently downgrade authority.

## A8 — Make the Claude Code product honest and self-diagnosing

- [ ] **A8.0 [CODEX] P0** Establish one runtime authority: the installed Forecost CLI owns the
      ledger and behavior; the Claude plugin remains a thin, versioned launcher/diagnostic with a
      separately checked protocol version.
- [ ] **A8.1 [CODEX] P0** Add `forecost setup claude --dry-run`, `--check`, and an isolated-config
      self-test. Implementation can be fully tested against temporary fake Claude config/cache.
- [ ] **A8.2 [CODEX] P0** Add `doctor --json` covering package version, transcript locations,
      plugin/manifest presence, hook executable, last hook heartbeat, ledger/outbox health,
      policy validity, source freshness, fail-open count, and protection capability.
- [ ] **A8.2A [CODEX] P0** Add `forecost self-test claude` to run the exact packaged launcher
      through the offline lifecycle simulator and report `simulation passed` separately from
      `real hook heartbeat observed`.
- [ ] **A8.3 [CODEX] P0** Make inactive protection visible: fail-open may allow the host to continue,
      but `doctor`/statusline must distinguish healthy, degraded, never-ran, and broken.
- [ ] **A8.4 [CODEX] P0** Replace the current generic preflight claim with a capability verdict:
      historical ledger ready, hooks active, current-turn observation available/unavailable,
      enforcement begins at which boundary, and “safe to walk away: YES/NO/BOUNDED.”
- [ ] **A8.4A [CODEX] P0** Standardize readiness as `NOT OBSERVED`, `OBSERVED`, or `CONTAINED`.
      Claude hooks alone may report `OBSERVED`; only an adapter with a tested binding real-time
      boundary may report `CONTAINED`.
- [ ] **A8.5 [CODEX] P0** Bind to real supported lifecycle points such as plan exit, tool completion,
      and stop only where payloads provide the needed facts; keep versioned fixture tests for
      each hook payload.
- [ ] **A8.5A [CODEX] P0** Cover current Claude lifecycle fixtures explicitly: `ExitPlanMode`,
      `Agent`, `SubagentStart/Stop`, `PostToolUse`, `PostToolBatch`, `PostToolUseFailure`,
      `StopFailure`, task creation/completion hints, interrupt, and background-agent settlement.
- [ ] **A8.5B [CODEX] P0** On `SessionEnd`, synchronously append only a tiny durable
      `settlement required` marker. Complete potentially lagging transcript reconciliation on the
      next SessionStart, doctor, receipt, or explicit ingest.
- [ ] **A8.6 [CODEX] P0** Before relevant tool gates, perform bounded incremental transcript ingest
      where safe; otherwise label control as settled-spend advisory.
- [ ] **A8.7 [CODEX] P1** Add a content-free statusline: run/turn identity, evidence freshness,
      settled vs reserved resources, last verified progress, and protection state.
- [ ] **A8.8 [CODEX] P1** Add a post-turn receipt summary and link/command to the full local receipt.
- [ ] **A8.9 [CODEX] P1** Match all relevant tool/MCP surfaces only after the hot check is O(1) and
      failure behavior is tested.
- [ ] **A8.10 [CODEX] P1** Version and validate marketplace/plugin manifests as part of the release
      artifact, not as branch-only files.

**Acceptance gate A8**

- [ ] One local self-test proves every installed hook executed and wrote a heartbeat/fixture event.
- [ ] A missing package, missing optional dependency, broken launcher, stale hook, or invalid
      policy produces an actionable diagnosis—not silent emptiness.
- [ ] Claude cannot be described as live hard-capped until a test demonstrates the exact boundary
      and maximum overrun.
- [ ] Statusline and synchronous gate latency meet published targets (initial target: p95 ≤50 ms
      warm and ≤150 ms cold on the supported baseline).

## A9 — Make privacy and integrity properties inspectable

- [ ] **A9.1 [CODEX] P0** Publish a field-level data inventory: source, type, normalization,
      persistence location, retention, export behavior, and user-facing alias.
- [ ] **A9.2 [CODEX] P0** Pseudonymize raw workspace/transcript paths, prompt/run IDs, cursors, and
      all open-ended identifiers; keep local display aliases separate and optional.
- [ ] **A9.3 [CODEX] P0** Route every persistent string—including guard, estimate, state, recovery,
      error, MCP, and legacy paths—through one privacy boundary.
- [ ] **A9.4 [CODEX] P0** Add `forecost privacy verify` to run canaries across ledger, outbox,
      spools, logs, exports, receipts, aliases, and migrations.
- [ ] **A9.5 [CODEX] P1** Add monotonic event sequence and chained digests so rewrite, deletion,
      truncation, and forked history are detectable.
- [ ] **A9.6 [CODEX] P1 — novel** Add optional local-key signed checkpoints and portable signed
      receipts. Keep unsigned/local-only state clearly labeled rather than implying trust.
- [ ] **A9.7 [CODEX] P1** Add `forecost verify` with `intact`, `truncated`, `rewritten`, `forked`,
      `unanchored`, and `unknown` states.
- [ ] **A9.8 [CODEX] P1** Harden all file operations against symlinks, unowned directories,
      permission races, oversized imports, decompression bombs, malformed JSON, and partial writes.
- [ ] **A9.9 [CODEX] P1** Define the same-user threat boundary explicitly: a hook cannot stop an
      agent with equivalent filesystem/process authority from disabling or editing it.

**Acceptance gate A9**

- [ ] A generated sentinel cannot be recovered from any persistent Forecost-owned file.
- [ ] Every ledger mutation class has a deterministic verification result.
- [ ] Privacy and integrity claims are test names and CLI results, not README adjectives.

## A10 — Production performance and self-observability

- [ ] **A10.1 [CODEX] P0** Maintain transactional settled/reserved rollups by relevant scope and
      time bucket; admission reads never scan the historical ledger.
- [ ] **A10.2 [CODEX] P0** Batch ingestion and bound every transaction, scan, in-memory result,
      transcript tail, and recovery pass.
- [ ] **A10.3 [CODEX] P0** Stream reconciliation and receipt generation; avoid loading all postings
      or estimates.
- [ ] **A10.4 [CODEX] P0** Replace heuristic N+1 estimate reconciliation with set-based exact run/
      span association and provisional finality.
- [ ] **A10.5 [CODEX] P1** Add structured local operational events: ingest attempt, watermark lag,
      callback result, outbox depth/age, replay/drop, fail-open, policy decision, reservation,
      reconciliation coverage, and receipt finalization.
- [ ] **A10.6 [CODEX] P1** Add `doctor` red/yellow/green rules and stable JSON fields for every
      operational signal.
- [ ] **A10.7 [CODEX] P1** Add 40k, 100k, 250k, and 1M event benchmarks for ingest, admission,
      reconciliation, run display, receipt, migration, and verification.
- [ ] **A10.8 [CODEX] P1** Establish latency/memory targets before optimization; fail CI on material
      regression with noise-tolerant thresholds.

**Acceptance gate A10**

- [ ] Admission is O(number of policy rules) and independent of event history.
- [ ] No supported push callback performs analytical SQLite work on an async event loop.
- [ ] A million-event ledger remains bounded in latency/memory according to published targets.
- [ ] Operators can distinguish zero usage from stale/broken ingestion.

## A11 — Exhaustive correctness, failure, and compatibility testing

- [ ] **A11.1 [CODEX] P0** Unit-test every pure identity, normalization, authority, valuation,
      matching, receipt, reservation, and conservation rule.
- [ ] **A11.2 [CODEX] P0** Add Hypothesis state machines for ledger writes, reconciliation finality,
      resource ownership, migrations, and crash/recovery.
- [ ] **A11.3 [CODEX] P0** Add multi-process concurrency tests, not only threads.
- [ ] **A11.4 [CODEX] P0** Add fault injection around filesystem, SQLite busy/full/corrupt states,
      process death, duplicated/late/out-of-order events, and interrupted migrations.
- [ ] **A11.5 [CODEX] P0** Add golden CLI tests for empty, first-use, degraded, partial-evidence,
      denied, expired, recovered, and tampered states.
- [ ] **A11.6 [CODEX] P0** Add exact built-wheel and installed-plugin E2E tests from an empty temp
      home; never test only editable source.
- [ ] **A11.7 [CODEX] P1** Test Python 3.10–3.13 and Linux/macOS/Windows; ensure copied/stale virtual
      environments are never part of the repository workflow.
- [ ] **A11.8 [CODEX] P1** Add mutation testing selectively for money, authority selection,
      reconciliation, privacy normalization, and reservations.
- [ ] **A11.9 [CODEX] P1** Add static type, lint, complexity, dead-code, secret, dependency, and
      artifact-content gates.
- [ ] **A11.10 [CODEX] P1** Preserve the critical invariant suite as release blockers, not optional
      benchmark jobs.
- [ ] **A11.11 [CODEX] P0** Block network access during unit, fixture, simulator, SDK-processor,
      replay, migration, privacy, and benchmark suites; any accidental external dependency fails
      the test.

**Acceptance gate A11**

- [ ] Every product claim maps to at least one installed-artifact E2E test.
- [ ] Every P0 failure mode has a deterministic reproduction and recovery assertion.
- [ ] Tests cover the new product path without requiring API keys or network access.

## A12 — Reproducible release and OSS adoption package

- [ ] **A12.1 [CODEX] P0** Make release validation compare source commit, wheel contents, version,
      changelog, plugin, marketplace, tag, and README install command.
- [ ] **A12.2 [CODEX] P0** Build artifacts from a clean checkout and install-test base plus every
      optional extra in isolated environments.
- [ ] **A12.3 [CODEX] P1** Add locked/hashed release constraints, SBOM, provenance/attestation
      generation, dependency audit, and reproducible-build evidence where feasible.
- [ ] **A12.4 [CODEX] P1** Write one 5-minute golden journey:
      `install -> forecost lab demo -> receipt latest -> doctor`.
- [ ] **A12.5 [CODEX] P1** Write one real-history journey and one graph-runtime integration journey.
- [ ] **A12.6 [CODEX] P1** Generate a deterministic terminal demo/GIF from the Run Lab, not hand-edited
      marketing output.
- [ ] **A12.7 [CODEX] P1** Publish the graph-chaos corpus, cap-soundness benchmark, receipt schema,
      and adapter conformance kit as the technical launch artifacts.
- [ ] **A12.8 [CODEX] P1** Add comparison documentation that says exactly where ccusage,
      AgentBudget, Langfuse, native runtimes, and Forecost are stronger.
- [ ] **A12.9 [CODEX] P1** Add focused issue templates, contributing guide, architecture tour,
      good-first-adapter workflow, and security disclosure instructions for the new kernel.
- [ ] **A12.10 [CODEX] P2** Prepare release notes, migration notes, announcement copy, example receipts,
      and benchmark methodology without publishing them.

**Acceptance gate A12**

- [ ] A stranger can install the exact artifact, see the new product in under five minutes,
      understand its evidence limits, and reproduce the headline benchmark.
- [ ] No release step depends on an ignored local file or stale built artifact.
- [ ] Publication remains the only external action left.

---

# Part II — founder decisions and work

These items should not be hidden inside engineering. Recommended defaults minimize the burden.

## F0 — Decisions needed before public positioning

- [ ] **F0.1 [FOUNDER]** Approve the first target: **API-billed teams running autonomous or
      multi-agent workflows**. Recommended: approve; do not target solo Claude subscription users
      as the primary customer.
- [ ] **F0.2 [FOUNDER]** Approve the first artifact: **graph-aware economic run receipt**.
      Recommended: approve; treat resource envelopes as conditional follow-on.
- [ ] **F0.3 [FOUNDER]** Approve legacy quarantine/removal. Recommended: keep read-only migration
      for one minor release, remove the old product from default help immediately.
- [ ] **F0.4 [FOUNDER]** Approve pseudonymizing workspace/transcript paths by default.
      Recommended: approve; optional local aliases can preserve usability.
- [ ] **F0.4A [FOUNDER]** Decide whether valid external W3C trace/span IDs may persist exactly or
      receive keyed local pseudonyms. Recommended: keyed pseudonyms by default, with an explicit
      interoperability mode for operators who need cross-system joins.
- [ ] **F0.5 [FOUNDER]** Approve the enforcement threat model. Recommended: interactive hooks
      fail open and admit same-user bypass; CI/gateway modes may fail closed only by explicit
      configuration and tested capability.
- [ ] **F0.5A [FOUNDER]** Approve readiness vocabulary `NOT OBSERVED / OBSERVED / CONTAINED`.
      Recommended: approve; prohibit Claude-only `CONTAINED` claims.
- [ ] **F0.6 [FOUNDER]** Decide whether the name “Forecost” remains appropriate once forecasting is
      removed. Recommended: retain temporarily to avoid brand churn; revisit only after field
      pull exists.
- [ ] **F0.7 [FOUNDER]** Approve outcome vocabulary and privacy-safe reason codes. Recommended:
      `good|bad|partial|unknown` plus independent evidence, never one synthetic success score.
- [ ] **F0.8 [FOUNDER]** Approve the public license/contribution stance for the receipt schema and
      conformance fixtures. Recommended: keep MIT code and make schemas/fixtures easy to adopt.

## F1 — Actions needed only at release or validation time

- [ ] **F1.1 [FOUNDER]** Decide when PR #2 and the future product branch are ready to merge.
- [ ] **F1.2 [FOUNDER]** Authorize/tag the release and PyPI/GitHub/Claude marketplace publication,
      or explicitly delegate those account-changing actions to Codex when ready.
- [ ] **F1.3 [FOUNDER]** Protect `main`, tags, release environments, and package publisher identity.
- [ ] **F1.4 [FOUNDER]** Review the final launch claims and example receipts for accuracy.
- [ ] **F1.5 [FOUNDER]** Decide whether to operate any community channel, roadmap, sponsorship, or
      support commitment. None is required for the local product to work.

---

# Part III — real-world and third-party validation

Codex can prepare fixtures, scripts, interview guides, telemetry definitions, and importers, but
these gates require actual external evidence.

## V0 — Product demand gate

- [ ] **V0.1 [FIELD]** Interview 12 maintainers/operators who run API-billed, parallel, or
      unattended agents. Ask for real incidents and current workarounds before presenting ideas.
- [ ] **V0.2 [FIELD]** Recruit 5 qualified design partners to install the receipt prototype.
- [ ] **V0.3 [FIELD]** Get at least 3 partners to generate receipts from their own real graphs.
- [ ] **V0.4 [FIELD]** Require at least 2 actionable discrepancies or changed run/model/workflow
      decisions before calling the receipt useful.
- [ ] **V0.5 [FIELD]** Require at least 3 users to keep it enabled for a second week.
- [ ] **V0.6 [FIELD]** Kill/reposition the receipt if fewer than 3 teams will connect two independent
      sources or nobody acts on a discrepancy.

## V1 — Resource-control gate

- [ ] **V1.1 [FIELD]** Collect at least 3 recurring fan-out/retry/parallel overrun incidents with
      enough detail to reproduce structurally.
- [ ] **V1.2 [FIELD]** Test whether native framework controls or AgentBudget already solve each
      incident acceptably.
- [ ] **V1.3 [FIELD]** Proceed with the envelope product only if Forecost's cross-process graph
      ownership closes a material, repeated gap.
- [ ] **V1.4 [FIELD]** Validate the displayed maximum overrun and stop semantics on real runtimes.

## V2 — Live accounting and ecosystem validation

- [ ] **V2.1 [FIELD]** Connect real OpenAI Costs/Usage and Anthropic Usage/Cost sources after offline
      importers pass conformance.
- [ ] **V2.2 [FIELD]** Validate service tiers, batch discounts, cache classes, tool charges,
      contracts, subscriptions, quotas, credits, adjustments, and late invoices against real
      accounts.
- [ ] **V2.3 [FIELD]** Validate OTel/Agents SDK/LangGraph/Claude/LiteLLM identities and finality
      against supported current versions.
- [ ] **V2.4 [FIELD]** Run an external security/privacy review before describing receipts as
      independently verifiable across trust boundaries.
- [ ] **V2.5 [FIELD]** Upstream or register schemas/adapters only after their maintainers accept the
      integration shape.
- [ ] **V2.6 [FIELD]** Publish to PyPI/GitHub/marketplace and verify from unrelated machines/accounts.

---

# Dependency-ordered execution batches

No implementation starts until the founder says to proceed.

## Batch 1 — truth + first useful offline receipt

- [ ] A0 product contract and ADRs.
- [ ] A1 truthful current/legacy boundary and packaging contract.
- [ ] A2 causal/economic kernel and migration plan.
- [ ] A3 Run Lab corpus and privacy canary.
- [ ] A4 `runs`, `receipt`, `mark`, and receipt diff against synthetic fixtures.
- [ ] A11 installed-artifact and failure tests for Batch 1.

**Outcome:** the repository demonstrates the intended product locally without credentials or
third parties.

## Batch 2 — independent evidence

- [ ] A5 reconciliation batches, offline provider/gateway importers, and discrepancy explainer.
- [ ] A7 adapter contract, Claude/LiteLLM corrections, OTel file receiver, and local fake runtime
      adapters.
- [ ] A8 setup/doctor/self-test and honest capability verdict.
- [ ] A9 privacy verify and integrity chain.
- [ ] A10 bounded performance and self-observability.

**Outcome:** the receipt is production-shaped and evidence-aware, though real provider validation
remains explicitly pending.

## Batch 3 — conditional resource control

- [ ] Execute A6 only after the local proof spike and field gate justify it.
- [ ] Integrate the proven envelope through A7/A8 capability-specific boundaries.
- [ ] Add conservation, chaos, maximum-overrun, and Cap Soundness Certificate release gates.

**Outcome:** a graph-aware governor with a narrower and more defensible guarantee than generic
per-process budget counters.

## Batch 4 — release and OSS launch preparation

- [ ] Complete A12 reproducible artifacts, documentation, demos, benchmarks, and migration.
- [ ] Complete all A11/P0 release blockers.
- [ ] Hand F1 publication decisions to the founder.
- [ ] Start V0/V1/V2 field gates; do not convert unvalidated synthetic success into marketing
      claims.

## Five-minute golden journey to build and test

- [ ] **Minute 0–1 [CODEX]:** install the exact wheel and run `forecost setup claude --dry-run`.
      Output says what would change, what remains unsupported, and that hooks do not guarantee
      current-model-call containment.
- [ ] **Minute 1–2 [CODEX]:** run `forecost self-test claude`. It proves the packaged launcher,
      simulator, privacy canary, and receipt path while keeping real heartbeat status separate.
- [ ] **Minute 2–3 [CODEX]:** run `forecost lab demo --adapter claude --scenario fanout` and show
      foreground/background branches, pending settlement, deterministic crash closure, and final
      receipt—all offline.
- [ ] **Minute 3–4 [CODEX]:** run `forecost doctor`; show `NOT OBSERVED` before a real hook and
      one exact next command. If an isolated real hook fixture is injected, transition to
      `OBSERVED`, never `CONTAINED`.
- [ ] **Minute 4–5 [CODEX]:** run `forecost receipt latest`; show authority, freshness, branches,
      failures, missing evidence, outcome tier, integrity state, and the current blind window.

**Golden-journey acceptance:** no API key, cloud account, provider connection, private transcript,
or manual config edit is required; every command runs against the installed artifact, not source.

---

# Master completion gates

- [ ] **G0 — Truth:** one product, one database, one version, one capability matrix.
- [ ] **G1 — Receipt:** a fresh install produces a meaningful content-free receipt in under five
      minutes, offline.
- [ ] **G2 — Evidence:** independent source completeness, authority, freshness, and residual are
      explicit and reproducible.
- [ ] **G3 — Privacy:** every persistent path passes the end-to-end sentinel and identifier audit.
- [ ] **G4 — Integrity:** mutation/truncation/fork states are detectable; signed state is never
      implied when absent.
- [ ] **G5 — Control:** if shipped, concurrent/retry/crash histories preserve the resource
      conservation invariant and declared maximum overrun.
- [ ] **G6 — Performance:** admission is history-independent; million-event operations meet
      published latency/memory targets.
- [ ] **G7 — Artifact:** the exact wheel/plugin release passes isolated install and lifecycle E2E
      tests on supported platforms.
- [ ] **G8 — Usefulness:** real teams generate repeated receipts and act on discrepancies.
- [ ] **G9 — Differentiation:** Forecost demonstrably solves a job not already satisfied by
      ccusage, AgentBudget, Langfuse, or native runtime telemetry.

## First action when implementation is authorized

Start **Batch 1** in a new product branch. Do not publish, connect accounts, contact users, or
build a dashboard. The first milestone is a complete offline vertical slice:

```text
forecost lab demo
forecost runs show latest
forecost receipt latest --json
forecost privacy verify
```

It must show causal structure, meter facts, valuation authority, evidence completeness,
discrepancy, outcome tier, and integrity state while proving that no prompt/tool/file content was
persisted.

## Standards and current product baselines

- [OpenAI Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/) and
  [usage](https://openai.github.io/openai-agents-python/usage/)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks),
  [status line](https://code.claude.com/docs/en/statusline), and
  [plugin reference](https://code.claude.com/docs/en/plugins-reference)
- [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
  and [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [FOCUS specification](https://focus.finops.org/focus-specification/) for cross-provider economic
  vocabulary
- [AgentBudget](https://agentbudget.dev/docs) as the direct budget-control baseline Forecost must
  beat on a demonstrated graph/distributed job rather than imitate
