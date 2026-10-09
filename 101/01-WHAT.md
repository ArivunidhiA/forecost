# What is Forecost?

Forecost is an independent record keeper for the economics of AI-agent runs.
Its primary artifact is a portable receipt, not a dashboard.

## The six jobs it performs

### 1. Represent the run's shape

Agent work is usually a graph rather than one API call. Forecost can retain
runs, spans, parent/child relationships, branches, attempts, links, fan-in,
waits, lifecycle states, and known gaps. This explains *why* a total has the
shape it does.

### 2. Record measured quantities

Adapters can contribute quantities such as input tokens, output tokens, calls,
or other bounded measurements. These are **meter facts**, not money.

### 3. Record monetary or quota valuations separately

A fact can have several valuations. A bundled rate table may calculate a
list-rate equivalent. LiteLLM may report a gateway estimate. An authenticated
provider source/profile may represent a provider-billed amount. Forecost records the authority,
currency, tariff provenance, finality, and source instead of treating every
number as interchangeable.

Current offline file import does not authenticate provider origin merely because
the caller selects a provider name. Every arbitrary JSON/CSV import is therefore
`user_imported_claim`. Schema v11 also append-supersedes proven historical local
imports that used the stronger `billed` label. An authenticated provider profile
still does not exist, so provider-billed claims remain unavailable.

### 4. Reconcile independent evidence

Reconciliation asks: which sources were expected, which appeared, what matched,
what remains unmatched, and what is the residual? It makes disagreements and
coverage gaps visible. It does not force unrelated observations to match.

### 5. Compare only when the evidence is actually matched

`forecost compare` refuses the tempting but invalid shortcut of subtracting any
two run totals. Its simple mode for valid existing run IDs always abstains. Its stricter experimental
mode requires predeclared, digest-bound matched cohorts and deterministic
test/build outcome evidence before it can evaluate an observational economic/outcome
policy. Version 1 requires at least 30 pairs and completely valued final `delta`
meters in USD list-rate scope. It validates a WAL-consistent in-memory copy of
the journal and derived projections, and it abstains if any non-journal-derived
reconciliation batch is present. It does not claim causal savings.

### 6. Produce durable, inspectable output

Receipts and comparison results can be rendered as terminal text, JSON, or
Markdown. The optional MCP surface is read-only and exposes run listing,
receipt retrieval, and an always-abstaining two-run comparison diagnostic. This
makes Forecost suitable for humans, scripts, and other agents without requiring
a hosted UI; it is not yet the proposed live budget/loop-control MCP.

## Main interfaces

| Interface | Purpose | Status |
| --- | --- | --- |
| `forecost` CLI | Primary user and operator interface | Unreleased experimental checkout |
| Text/JSON/Markdown receipts | Portable evidence artifacts | Implemented experimental views |
| Run Lab | Isolated deterministic scenarios | Supported synthetic evidence |
| Optional MCP server | Read-only run, receipt, and abstaining comparison-diagnostic access | Experimental optional extra; three tools |
| Claude Code hooks/plugin | Local lifecycle observation and policy | Experimental, fail-open |
| LiteLLM callback | Gateway observation | Experimental |
| OTel-style import | Offline causal evidence mapping | Experimental offline import |
| OpenAI Agents/LangGraph mappings | Contract tests against local fakes | Offline-only, not live support |
| `forecost legacy ...` | v0.2 CLI compatibility | Unsupported; CLI-isolated, but SDK exports still exist |

## Current command families

- **Explore:** `lab`, `runs`, `receipt`, `ledger`, `doctor`.
- **Bring in evidence:** `ingest`, `import`, `capture`, `mark`.
- **Compare and validate:** `compare`, `reconcile`, `verify`, `privacy`,
  `pricing-audit`, `adapters`, `calibration`.
- **Operate integrations:** `setup`, `statusline`, `self-test`, `recover`.
- **Experiment with limits:** `envelope`, `burn`.
- **Manage old data deliberately:** `migrate`, `purge`, `legacy`.

Run `forecost COMMAND --help` before using a mutating command. The root help
states the data-store boundary for every command.

## Product laws

The formal laws live in [`docs/product-contract.md`](../docs/product-contract.md).
In plain language they mean:

1. show evidence before advice;
2. require that current-product evidence state contain no prompts, completions,
   tool payloads, source code, credentials, or raw workspace paths; keyed
   cursor/error identities implement that current-path rule, while the exported
   legacy SDK/`costs.db` remains a blocking exception;
3. preserve causal identity before calculating aggregates;
4. do not confuse quantities with monetary values;
5. describe local controls only within their real boundary;
6. correct late evidence through new/superseding records, not silent rewriting;
7. prefer portable artifacts over another proprietary dashboard.

These are architectural constraints. A feature that violates one is not a
normal enhancement; it changes the product.
