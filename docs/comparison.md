# Where Forecost fits

This is a boundary comparison, not a claim that another project cannot add a
feature. Evaluate tools against their current documentation and your own data.

| Tool category | Usually answers | Forecost's different job |
| --- | --- | --- |
| Provider usage or billing export | What one provider reports for an account/window | Preserve that report as one authority and compare it with local/runtime/gateway evidence |
| Gateway cost dashboard | What passed through one gateway | Retain gateway valuation without treating unseen work or provider adjustments as covered |
| Trace/observability platform | What spans, logs, and payloads describe execution | Produce a portable content-free economic receipt with explicit evidence gaps |
| Harness-native token counter | What one agent runtime observed | Reconcile across runtimes and causal branches without merging retries or valuations |
| Local transcript usage viewer | What a local transcript exposes | Avoid persisting prompt/tool content and compare transcript evidence with independent sources |
| Budget callback or counter | Whether one integration crossed a local threshold | Prove single-host graph resource conservation while stating the boundary and maximum overrun |

Forecost is useful only when at least two independent sources or a graph-shaped
run make provenance, disagreement, retry identity, or missing evidence matter.
If one trustworthy provider total or a simple atomic counter answers the user's
question, those simpler tools are the correct baseline.

## Non-goals

- predicting the cost or quality of a future task;
- recommending models from observational spend;
- replacing traces, invoices, gateways, or framework controls;
- claiming provider-side enforcement from a local hook;
- storing prompts/tool payloads or operating a hosted dashboard.

The field validation gate in `docs/completion-checklist.md` requires real users
to demonstrate repeated discrepancies or control failures before these local
proofs become broad public product claims.
