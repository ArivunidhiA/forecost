# forecost

**The independent flight recorder for AI agent work.** It records what your coding
agents actually cost — across every harness and currency — reconciles the meters
nobody trusts, and (once it has earned the right to) briefs you before you launch an
expensive run. Local-first. Content-free. `pip install`, no signup, no cloud.

[![License: MIT](https://img.shields.io/github/license/ArivunidhiA/forecost)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/ArivunidhiA/forecost/ci.yml)](https://github.com/ArivunidhiA/forecost/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

> **Honest status.** The ledger, reconciliation, budget gate, and Claude Code plugin
> work today. The pre-execution **estimator runs in shadow mode** — it computes and
> records estimates but **displays nothing**, because on real data it hasn't yet cleared
> the accuracy bar we set for it (see [Calibration](#calibration-the-honest-part)).
> We'd rather show you a trustworthy ledger than an untrustworthy guess.

## What it does that other tools don't

Everyone can meter tokens. Two things are genuinely unoccupied, and forecost does both:

- **It's an independent second set of books.** Your Claude Code session says one number,
  the dashboard says another, LiteLLM says a third — and no vendor will audit its own
  meter. forecost reconciles them and shows you the disagreement.
- **It reads the harnesses where agentic spend actually happens.** It ingests Claude
  Code transcripts directly (no proxy, no API key), computing cost from tokens ×
  a bundled pricing table — because those transcripts carry no dollar field.

## Privacy is the whole point (and it's testable)

forecost's **ledger** (the `ingest` / hook path) is **content-free by construction**:
it stores token counts, models, timestamps, costs, and workspace paths — never your
prompts, completions, or tool output. This isn't a promise, it's a
[CI-enforced test](tests/test_privacy_canary.py): a sentinel string is planted in a
synthetic transcript's prompt, tool arguments, and output, and the test fails if it can
be found anywhere under `~/.forecost/`. The ledger has no cloud tier — there is nothing
to leave to.

**Two exceptions, both local-first opt-outs, not part of the ledger path:** the legacy
`forecost init --smart` command sends project excerpts (README, code snippets) to an LLM
provider to estimate scope — it asks for confirmation first and is entirely optional. And
the LiteLLM gateway adapter records the gateway's own `response_cost` figure (a number,
not content). Neither touches transcript content.

## Quickstart

```bash
pip install -e .        # from a clone; PyPI release coming

forecost ingest         # pull new usage from your Claude Code transcripts
forecost ledger status  # what you've spent, by model
forecost reconcile      # cross-check the ledger's internal consistency
forecost burn           # trailing burn rate → time-to-budget
```

```text
$ forecost ledger status
Ledger: 38,996 usage events, 70 workspaces, 97 sessions
Total USD spend (pricing_table + source_reported): 14164.05

Top models by spend:
  claude-opus-4-8       n=19616   USD 12092.45
  claude-sonnet-5       n=11367   USD  1394.43
  claude-haiku-4-5      n=502     USD     5.10
```

## Budget enforcement for Claude Code (the plugin)

forecost ships a Claude Code plugin (`plugin/`) that installs hooks:

- a **budget gate** — if a session crosses a hard limit you set in `.forecost.toml`, the
  next tool call is denied with a reason;
- a **threshold-gated preflight note** — on fan-out / scope-broadening prompts only
  (never on cheap turns — nobody wants another prompt to rubber-stamp);
- a **background reconciler** — every session end quietly ingests and scores itself.

Every hook is **fail-open by law**: if forecost breaks, your agent keeps working. A
broken forecost degrades to "no forecost," never to "no Claude Code."

```toml
# .forecost.toml
[[policy.rules]]
id = "session-cap"
scope = "session"
currency = "USD"
soft_limit = 5.0
hard_limit = 10.0
action = "deny"
```

## Works with your gateway too

If you run a [LiteLLM](https://github.com/BerriAI/litellm) proxy, forecost provides a
callback (`examples/litellm/`) that enforces the same budget on the money path and
records every call — with LiteLLM's own cost figure kept alongside forecost's, so the
two can be reconciled.

## Calibration — the honest part

We ran the estimator against 601 real prompt-turns of one heavy user's history. The
results, [published in full](experiments/calib/VERDICT.md):

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

The methodology is fully reproducible — [`experiments/calib/`](experiments/calib/) has
the extractor and backtest; run them against your own history.

## Command reference

| Command | What it does |
|---|---|
| `forecost ingest` | Pull new usage from Claude Code transcripts into the ledger |
| `forecost ledger status` / `by-workspace` | Spend totals, by model or project |
| `forecost reconcile` | Cross-check the ledger's internal consistency |
| `forecost calibration` | The estimator's accuracy record (shadow-mode) |
| `forecost burn` | Trailing burn rate, projected against your budgets |

<details>
<summary>Legacy commands (v0.2 — still work, being superseded)</summary>

The earlier calendar-forecasting product (`calc`, `price`, `forecast`, `track`, `watch`,
`optimize`, `serve`, `demo`, `init`, `export`) still ships and works. It's being
superseded by the ledger-based commands above; see
[the repositioning docs](#background) for why.

</details>

## Background

forecost started as a calendar-spend forecaster and was deliberately repositioned after
a long research effort concluded that (a) nobody wanted daily-spend forecasting and
(b) the interesting, unoccupied problems were reconciliation and pre-execution
briefing. The full research trail — including the agents that tried to *kill* the idea —
lives in the project's internal docs.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome — especially reports of
how ingestion and the hooks behave on *your* transcripts and harnesses.

## License

MIT
