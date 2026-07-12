"""Policy/budget engine: evaluates ledger spend against TOML-defined rules.

Pure function over (rules, ledger scope aggregates). Deterministic, read-only
via forecost.ledger.queries. Fail-open by law (BASEMENT.md L4 / Iron Rule #1
generalized): any internal exception here must resolve to 'allow', never
silently deny the host agent capability.
"""
