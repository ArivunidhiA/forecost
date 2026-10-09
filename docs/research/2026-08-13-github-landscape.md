# Forecost ecosystem landscape: 50 repositories

**Snapshot:** 2026-08-13  
**Purpose:** product, integration, security, DX, and distribution research for Forecost  
**Method:** repositories were screened for relevance, then current metadata and upstream documentation were inspected. This is **not** a historical GitHub Trending ranking: GitHub exposes no stable historical Trending API. Stars are volatile discovery signals, not proof of usage, retention, quality, or fit.

The supplied source document `https___github.docx` contains 14
hyperlinks: 12 unique repositories, one duplicate link marked important, and the
GitHub `code-quality` topic. All were screened; none should be vendored or
installed automatically.

## Decision summary

The landscape supports **improving and narrowing Forecost**, not abandoning it.

The broad ingredients already exist separately:

- [`ccusage`](https://github.com/ccusage/ccusage) owns simple, highly legible local coding-agent cost visibility.
- [`agentacct`](https://github.com/mikehasa/agentacct) documents an unusually close combination of local multi-source evidence, a work graph, metadata-only storage, outcomes, budgets, OTLP, and MCP.
- [`AgentBudget`](https://github.com/AgentBudget/agentbudget) documents live limits, nested budgets, and loop control.
- [Langfuse](https://github.com/langfuse/langfuse) and [Phoenix](https://github.com/Arize-ai/phoenix) cover broad tracing, agent graphs, evaluation, and observability.
- [`obsigna`](https://github.com/agent-receipts/obsigna), [`signet`](https://github.com/Prismer-AI/signet), and [`pipelock`](https://github.com/luckyPipewrench/pipelock) address signed receipts or realistic process-boundary threats.

Forecost therefore cannot credibly claim that local cost tracking, graph views, evidence joins, MCP, or signatures are unique. Its sharp opening is their intersection: **a neutral graph-economic assertion kernel that preserves competing authorities, enforces no-double-counting and branch-resource invariants, declares missing/stale/conflicting evidence, and turns the result into portable MCP and CI decisions.**

**Post-landscape implementation note:** the current worktree now has a narrow
read-only comparison v1. Two-run diagnostics always abstain; full CLI mode
requires digest-bound exact cohorts and a predeclared observational USD
list-rate policy with at least 30 pairs, predeclared deterministic test/build outcome evidence, and
confidence bounds. This is implementation evidence only. It has not passed the
head-to-head, independent-reproduction, demand, or retention gates described in
the startup-grade red team, and its third MCP tool is diagnostic rather than a
live control surface.

## Ten projects requiring continuous comparison

| Project | Upstream-documented strength | Forecost opening |
|---|---|---|
| [`agentacct`](https://github.com/mikehasa/agentacct) | Closest combination of local evidence, work graph, privacy mode, reporting, control, OTLP, and MCP | Demonstrate stricter economic/timing/resource invariants and portable assertion semantics |
| [`ccusage`](https://github.com/ccusage/ccusage) | One-command local cost UX, cache-aware accounting, compact/status-line modes | Explain branches, retries, authority disagreement, and evidence gaps instead of only totals |
| [`TokenTelemetry`](https://github.com/VasiHemanth/tokentelemetry) | Zero-config multi-agent local dashboard and waterfall | Keep a narrower content-free boundary; make causal-economic decisions portable |
| [`AgentBudget`](https://github.com/AgentBudget/agentbudget) | Live limits, loop detection, nested budgets, finalization reserve | Reconcile actual evidence after execution and remain runtime-neutral |
| [Langfuse](https://github.com/langfuse/langfuse) | Mature traces, agent graphs, evaluations, costs, integrations | Neutral, offline, content-minimized receipt and CI artifact instead of another trace UI |
| [Phoenix](https://github.com/Arize-ai/phoenix) | OTel/OpenInference tracing, experiments, evaluations, integrations | Assertion/reconciliation kernel above telemetry, not a competing viewer |
| [`AI Observer`](https://github.com/tobilg/ai-observer) | Local DuckDB observability, OTLP, and local imports | Stronger economic-authority semantics and a content-free default |
| [LiteLLM](https://github.com/BerriAI/litellm) | Gateway pricing, budgets, virtual keys, discounts, provider breadth | Reconcile gateway evidence with runtime and provider/invoice authorities |
| [`obsigna`](https://github.com/agent-receipts/obsigna) | Separate-daemon key boundary, Agent Receipts work, disclosure and anchor threat model | Export/integrate rather than invent a weaker signature envelope |
| [`pipelock`](https://github.com/luckyPipewrench/pipelock) | External mediation, provenance, signed action receipts, listener-binding defenses | Complement action integrity with causal-economic accounting |

### Feature-by-feature deep matrix

Every cell below is based on upstream documentation reviewed during this initial
landscape pass; no third-party runtime was exercised for the matrix itself.
A later, isolated v2 audit ran selected smoke tests for Arena, AgentAssay,
AgentBudget, and `agentacct`; those results are recorded separately in the
[startup-grade red team](2026-08-13-startup-grade-red-team-v2.md) and do not
retroactively prove matrix claims. “Not found” means **not found in the reviewed
public docs**, not proof the code lacks it.

| Project | Content/storage boundary | Graph semantics | Economic authority/reconciliation | Live control | Agent/MCP surface | CI assertions | Portable receipt / crypto | Completeness/evidence status |
|---|---|---|---|---|---|---|---|---|
| [`agentacct`](https://github.com/mikehasa/agentacct) | Local-first; documents `metadata_only_v1`; joins local client logs and work events | Work Graph, task sections, tool/work steps, machine checks | Client-reported usage, pricing estimates, provider/proxy evidence, attribution confidence, discrepancy/basis views | Budgets/stops only for owned or opt-in proxied processes | Eleven documented MCP tools for reports, events, checks, context, and value | Machine checks documented; a portable fail-closed cost/evidence Action was not found | Append-only Evidence v2 envelopes; cryptographic external anchor not found in reviewed docs | `complete/partial/unknown`; exact/high/medium/low joins; evidence matrix |
| [`ccusage`](https://github.com/ccusage/ccusage) | Reads local coding-client usage logs; compact terminal/status-line views | Time/model/session aggregation; no causal branch/retry DAG contract found | Cache-aware pricing-table totals; no reviewed multi-authority billed reconciliation contract | Display/status-line, not an admission/reservation control | No Forecost-like accounting MCP found | No receipt-policy assertion layer found | Reports/share output; signed receipt not found | No predeclared source-obligation completeness contract found |
| [`TokenTelemetry`](https://github.com/VasiHemanth/tokentelemetry) | Local dashboard; reviewed docs permit richer prompt/reasoning/response telemetry, so not content-free by default | Multi-agent waterfall/trace presentation | Token/cost and budget views; independent authority selection/reconciliation not found | Budget visualization/control claims; atomic branch conservation not found | No focused accounting MCP found | No portable assertion Action found | Signed economic receipt not found | Explicit claim-profile denominator/freshness contract not found |
| [`AgentBudget`](https://github.com/AgentBudget/agentbudget) | Runtime/library budget state; content boundary is not its primary documented promise | Nested budgets, retries/loops, finalization reserve | Prospective resource limits; post-run multi-source billing reconciliation not found | Strongest documented live limit/loop comparator | Agent integration documented; broad receipt-query MCP not the reviewed wedge | CI receipt/evidence assertions not found | Economic evidence receipt/signature not found | Control state rather than source-completeness accounting |
| [Langfuse](https://github.com/langfuse/langfuse) | Cloud/self-host trace system; traces can carry rich application/model content with controls | Mature traces, spans, agent graphs, evaluations | Token/cost tracking and custom pricing; neutral local runtime/gateway/invoice authority contract not found | Platform monitoring/evaluation; no local atomic branch reservation contract found | Agent-facing integrations; no reviewed four-call local cost-control contract | Evaluation/automation surfaces, not a receipt-bundle cost/retry/evidence gate | Exportable traces; signed content-free economic receipt not found | Trace/evaluation quality, not a predeclared economic source-obligation vector |
| [Phoenix](https://github.com/Arize-ai/phoenix) | OTel/OpenInference observability; spans may contain prompts, outputs, and attributes unless configured otherwise | Trace/span graphs, experiments, evaluations | Usage/cost observability; billed-authority reconciliation contract not found | Observe/evaluate, not local atomic budget admission | Integrations and tracing APIs; focused budget MCP not found | Eval workflows exist; portable receipt-policy assertion not found | Trace export; signed economic receipt not found | Telemetry/eval coverage rather than claim-profile completeness |
| [`AI Observer`](https://github.com/tobilg/ai-observer) | Local single-binary/DuckDB plus OTLP/local import; telemetry content depends on exporter | Local trace/waterfall views | Usage/cost view; authority/finality selection and invoice residual contract not found | Observation rather than admission control | Local interfaces; focused accounting MCP not found | Cost/retry/evidence Action not found | Cryptographic receipt not found | Source-obligation denominator/freshness contract not found |
| [LiteLLM](https://github.com/BerriAI/litellm) | Gateway sees proxied request/response data; logging/storage depends on deployment config | Request, retry/fallback, routing structure; not a general causal work DAG | Broad pricing, budgets, virtual keys, discounts, gateway `response_cost`; provider-invoice authority remains separate | Strong gateway-level spend/rate controls | Proxy APIs and MCP routing support; not the same as an independent receipt-control MCP | Budget checks can be scripted; portable graph/evidence receipt gate not found | Gateway logs/artifacts; neutral signed run receipt not found | Provider/gateway operational state, not a cross-source completeness contract |
| [`obsigna`](https://github.com/agent-receipts/obsigna) | Disclosure profiles, daemon/key boundary, optional protected payload handling | Agent Receipt actions/relationships rather than cost-specific DAG accounting | Economic authority selection, cache tariff, and invoice reconciliation are not its primary documented layer | Signing/anchor workflow, not live budget reservation | Protocol/daemon integration; live graph-cost MCP not found | Verification can fit CI; cost/retry/evidence predicates are outside reviewed scope | Strongest reviewed portable receipt, canonicalization/disclosure/anchor direction | Cryptographic/disclosure status; source-obligation economic completeness remains complementary |
| [`pipelock`](https://github.com/luckyPipewrench/pipelock) | External mediation boundary; observes/controls tool/network activity according to policy | Tool-call provenance/action sequence; no reviewed cost critical-path invariant | Graph-economic multi-authority reconciliation not found | Strong mediation/policy boundary and listener-binding controls | MCP proxy/mediation is central | Security policy checks; economic receipt assertion layer not found | Signed action/provenance receipt direction | Action integrity/provenance rather than billing-source completeness |

This comparison sharpens the integration strategy: consume LiteLLM/OTel/provider evidence; learn daily UX from `ccusage`; prove differentiated invariants against `agentacct` and AgentBudget; and interoperate with `obsigna`/Sigstore-style signing rather than claiming that any one of those ingredients is new.

## Closest comparison: `agentacct`

Current GitHub metadata at the snapshot: created 2026-07-24, 585 stars, MIT license, and pushed on 2026-08-13. These are repository facts, not an independent runtime evaluation.

The upstream [reference](https://github.com/mikehasa/agentacct/blob/main/docs/reference.md), [multi-source evidence architecture](https://github.com/mikehasa/agentacct/blob/main/docs/multi-source-evidence-architecture.md), [usage truth table](https://github.com/mikehasa/agentacct/blob/main/docs/usage-truth-table.md), [privacy threat model](https://github.com/mikehasa/agentacct/blob/main/docs/multi-source-privacy-threat-model.md), and [task/control plane](https://github.com/mikehasa/agentacct/blob/main/docs/task-control-plane.md) document:

- local Claude/Codex task and cost reporting;
- local-log usage plus machine-observed checks;
- `exact`, `high`, `medium`, and `low` attribution labels;
- append-only Evidence v2 envelopes;
- Work Graph, Evidence Matrix, discrepancies, and cost/outcome basis;
- a `metadata_only_v1` profile;
- OTLP and provider-proxy evidence;
- budgets for processes it owns; and
- `complete`, `partial`, and `unknown` evidence status.

Its public reference lists eleven MCP tools: `agentacct_list_runs`, `agentacct_get_report`, `agentacct_record_event`, `agentacct_attach_client_context`, `agentacct_record_section`, `agentacct_record_agent_usage_debug`, `agentacct_list_events`, `agentacct_get_event_summary`, `agentacct_record_machine_check`, `agentacct_prepare_judge`, and `agentacct_compute_value`.

This initial documentation study did **not** execute the project, validate its
joins, test concurrent budget behavior, or verify its privacy properties. A
later separate specialist executed three selected local MCP tests; that smoke
does not validate joins, concurrency, privacy, live clients, or headline claims.
“Documented” must not become “externally reproduced.”

Three Forecost invariants were not visible in the reviewed `agentacct` documentation. Absence from docs is not proof of absence from code:

1. **Same-fact, multi-authority no-double-counting.** Forecost tests retain multiple valuations for one fact while selecting one canonical charge; agentacct documents basis and discrepancies, but no reviewed invariant specified canonical selection among local, gateway, and billed versions of the same charge.
2. **Overlap-safe wall timing with explicit abstention.** Forecost tests union classified service and wait intervals so enclosing, adjacent, parallel, and fan-in spans do not double-count within a category; elapsed is a separately named envelope. Current structural edges cannot justify a non-trivial critical path, so Forecost withholds it instead of undercounting sequential siblings. The reviewed agentacct Work Graph docs did not specify these invariants.
3. **Atomic cross-process graph resource conservation.** Forecost tests concurrent parent/child admissions and splits so branches cannot allocate beyond the parent; the reviewed agentacct docs did not visibly expose a linearizable conservation invariant.

These are promising only after they work on real Claude/Codex/LangGraph histories and change user decisions.

## Relevance-screened 50-repository inventory

| # | Repository | Stars | Category | Forecost relevance |
|---:|---|---:|---|---|
| 1 | [`ccusage/ccusage`](https://github.com/ccusage/ccusage) | 17,893 | Cost | Daily cost UX/status-line baseline |
| 2 | [`VasiHemanth/tokentelemetry`](https://github.com/VasiHemanth/tokentelemetry) | 309 | Cost | Multi-agent local waterfall and budgets |
| 3 | [`mikehasa/agentacct`](https://github.com/mikehasa/agentacct) | 585 | Cost/evidence | Closest direct competitor |
| 4 | [`luoyuctl/agenttrace`](https://github.com/luoyuctl/agenttrace) | 119 | Observability | Local coding-agent trace baseline |
| 5 | [`tobilg/ai-observer`](https://github.com/tobilg/ai-observer) | 267 | Observability | OTLP plus local-file ingestion |
| 6 | [`langfuse/langfuse`](https://github.com/langfuse/langfuse) | 33,047 | Observability | Mature graph/cost/evaluation platform |
| 7 | [`Arize-ai/phoenix`](https://github.com/Arize-ai/phoenix) | 11,033 | Observability | OTel/OpenInference integration benchmark |
| 8 | [`traceloop/openllmetry`](https://github.com/traceloop/openllmetry) | 7,376 | Observability | GenAI OTel instrumentation |
| 9 | [`openlit/openlit`](https://github.com/openlit/openlit) | 2,685 | Observability | Open-source cost/performance platform |
| 10 | [`Helicone/helicone`](https://github.com/Helicone/helicone) | 6,063 | Observability | Proxy-based LLM telemetry |
| 11 | [`AgentOps-AI/agentops`](https://github.com/AgentOps-AI/agentops) | 5,771 | Observability | Agent-session monitoring |
| 12 | [`BerriAI/litellm`](https://github.com/BerriAI/litellm) | 56,261 | Gateway/cost | Pricing, budgets, provider normalization |
| 13 | [`AgentBudget/agentbudget`](https://github.com/AgentBudget/agentbudget) | 107 | Control | Live limits and loop detection |
| 14 | [`agent-receipts/obsigna`](https://github.com/agent-receipts/obsigna) | 20 | Receipts | Protocol and threat-model comparison |
| 15 | [`Prismer-AI/signet`](https://github.com/Prismer-AI/signet) | 37 | Receipts | Signed tool-call receipt comparison |
| 16 | [`luckyPipewrench/pipelock`](https://github.com/luckyPipewrench/pipelock) | 795 | Security | External mediation and signed actions |
| 17 | [`emiliaprotocol/emilia-protocol`](https://github.com/emiliaprotocol/emilia-protocol) | 844 | Protocol | Agent identity/trust interoperability |
| 18 | [`sigstore/cosign`](https://github.com/sigstore/cosign) | 6,205 | Signing | Established CI/artifact signing path |
| 19 | [`slsa-framework/slsa-github-generator`](https://github.com/slsa-framework/slsa-github-generator) | 591 | Provenance | Build-provenance reference |
| 20 | [`step-security/harden-runner`](https://github.com/step-security/harden-runner) | 1,243 | CI security | GitHub Action hardening/adoption pattern |
| 21 | [`anthropics/claude-code`](https://github.com/anthropics/claude-code) | 141,333 | Runtime | Primary integration surface |
| 22 | [`openai/codex`](https://github.com/openai/codex) | 105,706 | Runtime | Primary integration surface |
| 23 | [`openai/openai-agents-python`](https://github.com/openai/openai-agents-python) | 28,613 | Runtime | API-billed agent instrumentation target |
| 24 | [`modelcontextprotocol/python-sdk`](https://github.com/modelcontextprotocol/python-sdk) | 24,000 | MCP | Python implementation baseline |
| 25 | [`modelcontextprotocol/typescript-sdk`](https://github.com/modelcontextprotocol/typescript-sdk) | 13,160 | MCP | TypeScript implementation baseline |
| 26 | [`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers) | 89,534 | MCP | Packaging/discoverability pattern |
| 27 | [`langchain-ai/langgraph`](https://github.com/langchain-ai/langgraph) | 39,621 | Runtime | Graph/retry/checkpoint integration target |
| 28 | [`microsoft/autogen`](https://github.com/microsoft/autogen) | 60,401 | Runtime | Multi-agent graph stress target |
| 29 | [`crewAIInc/crewAI`](https://github.com/crewAIInc/crewAI) | 57,034 | Runtime | Persona/team integration target |
| 30 | [`pydantic/pydantic-ai`](https://github.com/pydantic/pydantic-ai) | 19,270 | Runtime | Typed-agent integration target |
| 31 | [`google/adk-python`](https://github.com/google/adk-python) | 21,092 | Runtime | Cross-provider agent runtime |
| 32 | [`github/github-mcp-server`](https://github.com/github/github-mcp-server) | 32,220 | MCP | First-party MCP UX/security reference |
| 33 | [`upstash/context7`](https://github.com/upstash/context7) | 60,685 | MCP | Focused MCP adoption reference |
| 34 | [`oraios/serena`](https://github.com/oraios/serena) | 27,963 | MCP | Coding-agent MCP workflow reference |
| 35 | [`msitarzewski/agency-agents`](https://github.com/msitarzewski/agency-agents) | 145,054 | Growth | Browsable persona/community flywheel |
| 36 | [`anthropics/skills`](https://github.com/anthropics/skills) | 168,836 | Skills | Official portable skill format |
| 37 | [`obra/superpowers`](https://github.com/obra/superpowers) | 271,600 | Skills | Auto-active methodology/plugin growth |
| 38 | [`mattpocock/skills`](https://github.com/mattpocock/skills) | 216,045 | Skills | Composable, editable, fast install |
| 39 | [`alirezarezvani/claude-skills`](https://github.com/alirezarezvani/claude-skills) | 24,378 | Skills | Cross-agent skill distribution |
| 40 | [`ComposioHQ/awesome-claude-skills`](https://github.com/ComposioHQ/awesome-claude-skills) | 72,418 | Discovery | Skill catalog/discovery channel |
| 41 | [`punkpeye/awesome-mcp-servers`](https://github.com/punkpeye/awesome-mcp-servers) | 92,222 | Discovery | MCP catalog launch channel |
| 42 | [`hesreallyhim/awesome-claude-code`](https://github.com/hesreallyhim/awesome-claude-code) | 52,240 | Discovery | Claude Code distribution channel |
| 43 | [`ruvnet/ruflo`](https://github.com/ruvnet/ruflo) | 67,766 | Orchestration | Swarm/branch stress fixture |
| 44 | [`JuliusBrussee/caveman`](https://github.com/JuliusBrussee/caveman) | 97,958 | Growth/DX | Memorable onboarding reference |
| 45 | [`firecrawl/firecrawl`](https://github.com/firecrawl/firecrawl) | 166,814 | Research | Structured web-research utility |
| 46 | [`unclecode/crawl4ai`](https://github.com/unclecode/crawl4ai) | 78,023 | Research | Local crawler/research utility |
| 47 | [`D4Vinci/Scrapling`](https://github.com/D4Vinci/Scrapling) | 73,797 | Research | Structured extraction utility |
| 48 | [`assafelovic/gpt-researcher`](https://github.com/assafelovic/gpt-researcher) | 28,957 | Research | Multi-source research workflow |
| 49 | [`vladkens/twscrape`](https://github.com/vladkens/twscrape) | 2,676 | Social research | X scraping/account rotation; policy risk |
| 50 | [`praw-dev/praw`](https://github.com/praw-dev/praw) | 4,224 | Social research | Preferable Reddit API client |

The final six research/scraping projects are references, not recommended Forecost dependencies. A scraper does not remove platform terms, authentication, rate limits, provenance, or selection bias.

## Supplied DOCX: current 14-link triage

| Repository/topic | Use decision | Useful pattern or caution |
|---|---|---|
| [`karpathy/llm-council`](https://github.com/karpathy/llm-council) | Concept only | Multi-evaluator comparison UX; no reviewed license, and an LLM council is not truth |
| [`ar9av/obsidian-wiki`](https://github.com/ar9av/obsidian-wiki) | Later if measured | Fast setup, plain-file ownership, explicit extracted/inferred/ambiguous states |
| [`JuliusBrussee/caveman`](https://github.com/JuliusBrussee/caveman) | Methods now | Slogan, autodetection, visuals, pinned benchmarks, and honest caveats; do not copy BSL-covered code |
| [`usestrix/strix`](https://github.com/usestrix/strix) | Clean-room methods now | Staged budget enforcement and security/CI presentation; not a core dependency |
| [`asgeirtj/system_prompts_leaks`](https://github.com/asgeirtj/system_prompts_leaks) | Never use | Do not ingest, train on, benchmark with, copy, or redistribute leaked prompts |
| [`mattpocock/skills`](https://github.com/mattpocock/skills) | Methods now; linked twice | Progressive disclosure, composable skill, and marketplace packaging; verify exact MIT revision |
| [`alirezarezvani/claude-skills`](https://github.com/alirezarezvani/claude-skills) | Later | Cross-agent packaging/community schema after the first supported host is stable |
| [`ruvnet/ruflo`](https://github.com/ruvnet/ruflo) | Competitor/stress evidence | Swarm/graph stress cases; broad cost/budget/loop features are commodity; never a core dependency |
| [`AgriciDaniel/claude-obsidian`](https://github.com/AgriciDaniel/claude-obsidian) | Methods now | Deterministic self-auditing artifacts and reversible transaction/release patterns |
| [`open-jarvis/OpenJarvis`](https://github.com/open-jarvis/OpenJarvis) | Later | Clean-room structural calibration methodology only after field evidence; contentful learning violates the default boundary |
| [`trimstray/the-book-of-secret-knowledge`](https://github.com/trimstray/the-book-of-secret-knowledge) | Discovery only | Validate every command against a canonical source; do not copy a command collection into runtime code |
| [`zhaoxuya520/reverse-skill`](https://github.com/zhaoxuya520/reverse-skill) | Clean-room methods now | Config-routing regression and evidence-review patterns; exclude GPL/offensive subtrees |
| [GitHub `code-quality` topic](https://github.com/topics/code-quality) | Discovery only | Use canonical projects and exact pinned tools; a topic is not a vetted dependency list |

## Adoption patterns worth copying

These are observed product mechanics, not proven causes of stars:

- Persona and skill collections make contribution cheap, artifacts browsable, and use cases easy to imagine.
- `ccusage` avoids a daemon decision, offers a transient invocation path, and remains visible through a compact status line.
- Focused MCP projects use one memorable job, short install paths, strong metadata, and inclusion in discovery catalogs.
- Memorable developer tools show the payoff before configuration, autodetect the environment, use visuals, publish honest caveats, and make uninstall obvious.

The proposed Forecost flywheel is:

1. Official Claude/Codex integration plus one portable Forecost skill.
2. A realistic graph receipt in under 60 seconds, then an optional import of the user's latest safe local run.
3. Status-line budget state and automatic end-of-run receipt create repeated exposure.
4. A redacted local Markdown/SVG card makes retry tax and evidence gaps shareable without a hosted upload.
5. A conformance kit and “Forecost-compatible” badge make adapters the easiest community contribution.
6. A GitHub Action produces a check summary and artifact without comment spam.
7. Public chaos/golden fixtures let runtime and adapter authors demonstrate compatibility.

Measure install completion, time to first receipt, second receipt within seven days, week-four retention, intended vs actual MCP calls, actionable discrepancies, persistent CI gates, and external adapters. Stars are secondary.

## Sources and interpretation boundaries

- Project descriptions above are based on linked upstream documentation unless explicitly called a local Forecost invariant.
- The initial 50-repository screen installed nothing. A later v2 specialist used
  isolated temporary checkouts/environments for narrow smoke tests; no
  third-party code was added to Forecost or made a runtime dependency.
- The supplied DOCX and shortlist informed discovery; no scraping repository was
  needed to replace direct GitHub and first-party documentation checks.
- Product claims should say “documents” or “claims” until a competitor behavior has been independently reproduced.
