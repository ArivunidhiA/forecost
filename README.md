# forecost

**The independent economic receipt for AI-agent runs.** Forecost records the
content-free causal graph behind a run, keeps meter facts separate from their
valuations, and shows what local runtimes, gateways, and provider exports agree
or disagree about. Local-first. No signup. No cloud.

[![License: MIT](https://img.shields.io/github/license/ArivunidhiA/forecost)](https://github.com/ArivunidhiA/forecost/blob/main/LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/ArivunidhiA/forecost/ci.yml)](https://github.com/ArivunidhiA/forecost/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

> **Honest status.** The graph-aware receipt, offline reconciliation importer,
> and single-host resource envelope are experimental local features. They are
> covered by deterministic synthetic tests today; live provider HTTP ingestion and distributed
> enforcement are deliberately not claimed. Calendar forecasting is legacy.

## What it does that other tools don't

Everyone can meter tokens. Two things are genuinely unoccupied, and forecost does both:

- **It keeps evidence separate.** Token observations, gateway estimates,
  list-rate equivalents, and provider-billed exports are distinct facts—not one
  misleading “cost” total.
- **It explains the run shape.** A receipt retains branches, retries, fan-in,
  waits, finality, outcome evidence, and known blind spots without prompts or
  tool payloads.

## Privacy is the whole point (and it's testable)

forecost's **ledger** (the `ingest` / hook path) is **content-free by construction**:
it stores token counts, models, timestamps, valuations, and pseudonymous workspace
identities — never your prompts, completions, tool output, or raw workspace paths.
This boundary is enforced by typed ingestion and a
[CI-enforced test](https://github.com/ArivunidhiA/forecost/blob/main/tests/test_privacy_canary.py): a sentinel string is planted in a
synthetic transcript's prompt, tool arguments, and output, and the test fails if it can
be found in Forecost-owned local state. Forecost has no hosted tier and the supported
product performs no network-backed ingestion. The retired `init --smart` upload path has
been removed. A LiteLLM adapter may retain the gateway's numeric `response_cost` evidence;
it never needs prompt or completion content.

## Quickstart

```bash
git clone https://github.com/ArivunidhiA/forecost
cd forecost
pip install -e .

forecost lab demo       # a complete synthetic graph receipt; no home data read
forecost lab chaos      # deterministic fan-out/cancellation fixture
forecost envelope --help
```

```text
$ # Synthetic example — these are not real usage or engineering values.
$ forecost ledger status
Ledger: 42 usage events, 3 workspaces, 5 sessions
Canonical USD valuation: 12.34

Top models by spend:
  example-model-a                          n=30     USD 10.00
  example-model-b                          n=12     USD 2.34
```

## Local Claude Code observation and controls (experimental plugin)

forecost ships an experimental Claude Code plugin (`plugin/`) that installs local hooks:

- a **policy check** — a healthy local hook can return an `ask` or `deny`
  decision after an observed threshold in `~/.forecost/policy.toml`;
- a **threshold-gated preflight note** — on fan-out / scope-broadening prompts only
  (never on cheap turns — nobody wants another prompt to rubber-stamp);
- a **background reconciler** — every session end quietly ingests and scores itself.

Every hook is intentionally fail-open: if Forecost is absent, stale, or broken, the
agent keeps working. This is local best-effort containment—not provider-side or
distributed enforcement—and maximum overrun is not bounded.

```toml
# ~/.forecost/policy.toml
[[policy.rules]]
id = "session-cap"
scope = "session"
currency = "USD"
soft_limit = 5.0
hard_limit = 10.0
action = "deny"
```

Repository-local `.forecost.toml` policy is ignored by default so a cloned
repository cannot silently impose enforcement. Set
`FORECOST_TRUST_PROJECT_POLICY=1` only when you deliberately trust that file.

## Works with your gateway too

If you run a [LiteLLM](https://github.com/BerriAI/litellm) proxy, Forecost provides an
experimental callback (`examples/litellm/`) that observes calls. LiteLLM's numeric cost
estimate remains separate from Forecost's list-rate valuation so they can be reconciled.
It does not claim distributed containment or provider-billed authority.

## Calibration — the honest part

We ran the estimator against 601 real prompt-turns of one heavy user's history. The
results, [published in full](https://github.com/ArivunidhiA/forecost/blob/main/experiments/calib/VERDICT.md):

| Target | Coverage of the P90 band | Interval width | Verdict |
|---|---|---|---|
| Cost | 88% (want 85–95%) ✓ | 8.5× (want ≤4×) ✗ | **too wide to show** |
| Duration | 88% ✓ | 10.7× ✗ | **too wide to show** |
| Files touched | 85% ✓ | 9.6× ✗ | **static flags only** |
| Mid-run "error-dense turn?" flag | see caveat below | — | **shadow only** |

So the estimator stays in shadow mode and the brief displays no ranges — that's a
pre-commitment kept, not a feature missing.

**About that mid-run flag — the honest caveat.** The backtest reported "67% precision at
a 2% flag rate," but that number is not yet trustworthy: the detector flags error-dense
turns, and the weak labels it was scored against were themselves *defined* by errors — so
numerator and denominator share one signal. Of the 12 flagged turns, 8 were merely
"ambiguous" and **0** were confirmed failures; there are no independent stuck/failure
labels in the corpus yet. So the guard ships **shadow-only** (computed, never surfaced)
until it can be scored against real user marks, exactly like the cost estimator. As real
usage accumulates, `forecost calibration` tracks whether any of these earn a place on
screen.

The methodology is fully reproducible — [`experiments/calib/`](https://github.com/ArivunidhiA/forecost/tree/main/experiments/calib) has
the extractor and backtest; run them against your own history.

## Command reference

| Command | What it does |
|---|---|
| `forecost lab demo` | Create a complete, isolated synthetic receipt |
| `forecost runs list` / `show` | Inspect a content-free causal graph |
| `forecost receipt <run>` | Render stable text, JSON, or Markdown evidence |
| `forecost capture <run> --kind test -- <command>` | Record only a local test/build exit and Git identity as outcome evidence |
| `forecost adapters check` | Inspect versioned adapter capability/conformance evidence |
| `forecost statusline` | Render bounded Claude observation health (`NOT OBSERVED` / `OBSERVED` / `CONTAINED`) |
| `forecost reconcile import` / `run` | Compare local valuations with offline exports |
| `forecost envelope` | Exercise experimental local reservations and leases |
| `forecost ingest` / `ledger` | Existing Claude Code transcript ledger (experimental adapter) |

The optional MCP server exposes exactly two canonical, read-only tools:
`forecost_list_runs` and `forecost_get_receipt`. Install `forecost[mcp]` and launch it
with `python -m forecost.mcp_launcher`; the base wheel does not advertise a broken
optional console script. MCP never opens the retired `costs.db` store.

<details>
<summary>Unsupported legacy commands (v0.2 compatibility)</summary>

The earlier calendar-forecasting product is quarantined under `forecost legacy`
(`calc`, `price`, `forecast`, `track`, `watch`, `optimize`, `demo`,
`init`, `export`) and will be removed before 1.0. It is not part of the current
receipt product, has no hidden root-command aliases, and uses the separate legacy
`~/.forecost/costs.db` store. The old local HTTP server has no CLI registration and the old
`init --smart` network/upload option no longer exists. See
[the repositioning docs](#background) for why.

</details>

## Background

forecost started as a calendar-spend forecaster and was deliberately repositioned after
a long research effort concluded that (a) nobody wanted daily-spend forecasting and
(b) the interesting, unoccupied problems were reconciliation and pre-execution
briefing. The full research trail — including the agents that tried to *kill* the idea —
lives in the project's internal docs.

## Contributing

See [CONTRIBUTING.md](https://github.com/ArivunidhiA/forecost/blob/main/CONTRIBUTING.md) and the
[architecture/product laws](https://github.com/ArivunidhiA/forecost/blob/main/docs/architecture.md). Issues and PRs are especially
welcome for new harness adapters, using synthetic fixtures—never private transcripts.

## License

MIT
