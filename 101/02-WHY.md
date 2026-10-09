# Why does Forecost exist?

## The accounting gap

Most AI tooling can count something, but each observer sees only its own slice.
A local harness may know tokens but not billed dollars. A gateway may know calls
that passed through it but not calls that bypassed it. An authenticated provider
source/profile may be authoritative for a billing window but may not describe
the causal branches that produced the total.

This creates four recurring problems:

1. **Provenance loss:** a dashboard shows `$12.34` without explaining which
   source asserted it.
2. **Double-counting:** two valuations of the same event are added as if they
   were two events.
3. **Graph loss:** retries and branches disappear inside an aggregate.
4. **False certainty:** incomplete or provisional evidence is described as
   “actual,” “verified,” or “complete.”

Forecost exists to preserve the distinctions needed to avoid those errors.

## Why privacy changes the architecture

Traditional tracing products often collect prompts, completions, tool bodies,
or logs because content helps debugging. Forecost's job is narrower: economic
and causal evidence. Its typed ingestion contracts reject content-shaped fields
and current Claude cursor/error paths use installation-keyed HMAC identities or
finite fingerprints. This is still not an end-to-end privacy guarantee: the
exported legacy SDK can write arbitrary project names, paths, and metadata to
`costs.db`, custom paths outside `FORECOST_HOME` are not discoverable as a
closed set, and same-UID code can read or replace local state.

The benefit is that teams can study cost shape and evidence disagreement
without building another database of sensitive prompts and code. The tradeoff
is intentional: Forecost cannot answer content-debugging questions and should
not pretend to replace a trace viewer.

## Why a graph instead of a list of calls

Suppose three subagents run in parallel, one retries, and a parent waits for all
of them. A flat list can calculate a total, but it cannot reliably explain:

- which operation caused the retry;
- whether two events are duplicates or separate attempts;
- what was parallel versus sequential;
- which missing child makes the evidence incomplete;
- which resource reservation belonged to which branch.

Stable run/span identity and causal links make those questions answerable.

## Why not just trust the provider bill?

If one provider total is all you need, the provider report is simpler and is
the right tool. Forecost becomes useful when at least two independent sources,
or a graph-shaped run, make missing evidence, retry identity, provenance, or
disagreement important.

The provider bill and Forecost solve different parts of the problem:

| Provider/export | Forecost |
| --- | --- |
| Account/window billing authority | Run-level causal and source evidence |
| Usually provider-specific | Can compare runtime, gateway, rate-table, and export claims |
| May include adjustments | Preserves adjustments as authority-specific evidence |
| Does not necessarily explain agent branches | Retains graph topology when observed |

## Why forecasting was demoted

The project originally focused on forecasting future calendar spend. Research
and calibration changed that direction. Daily-spend forecasting did not prove a
strong user job, and the task-level estimator's intervals were too wide to be
useful. The project kept the evidence ledger and reconciliation work because
those capabilities were both more defensible and less occupied.

The estimator still computes in shadow mode so it can be evaluated honestly,
but the current product refuses to display weak ranges as advice. This is an
example of the first product law: evidence before advice.

## When Forecost is the wrong tool

Use something simpler when:

- one trustworthy counter or provider total answers the question;
- you need prompt-level debugging or full distributed tracing;
- you need a hosted, multi-tenant dashboard;
- you need provider-side spending guarantees;
- you want future task-cost predictions today;
- you need Forecost to judge whether an agent's answer is correct.
