# forecost — Claude Code plugin

Runs Forecost's experimental fail-open hooks inside Claude Code. The hooks append
content-minimizing local observations under the intended contract, evaluate local policy when evidence is healthy,
and accrue a shadow calibration record. Missing, stale, or broken observation
degrades to no Forecost decision; it never claims provider-side containment.

## What it wires

| Hook event | What forecost does |
|---|---|
| `SessionStart` | Attempts to register an observed session/workspace using the explicitly installed `forecost-hook`. |
| `UserPromptSubmit` | Records a shadow estimate and may return a local policy decision when its evidence is healthy. |
| `PreToolUse` (all tool/MCP surfaces) | Performs the cached O(1) local policy check; `ask`/`deny` is neither distributed nor provider-side enforcement. |
| `PostToolUse` / `PostToolUseFailure` | Asynchronously records bounded tool lifecycle; `ExitPlanMode` and `Agent` retain structural kinds. |
| `SubagentStart` / `SubagentStop` / `StopFailure` | Asynchronously records the lifecycle event when Claude supplies it. |
| `Stop` | Asynchronously ingests the transcript delta, reconciles evidence, and updates the bounded post-turn summary. |
| `SessionEnd` | Synchronously writes only a tiny fsynced pending-settlement marker; idempotent reconciliation follows separately. |

The current capability boundary is published in `docs/capabilities.json`.
Trace-scoped graph identity and explicit timing semantics are implemented in the
current receipt-v2 worktree, but have not been validated against a supported
live Claude profile. An arbitrary offline export is only a user-imported claim,
not authenticated provider-billed evidence, and maximum provider/distributed
overrun is not bounded.

## Installation status: unavailable

Forecost 0.3.0 is unreleased and is not available from PyPI or a supported
Claude marketplace entry. The `forecost` package currently on PyPI is the
retired 0.1.1 forecasting product. Do not use it to install this plugin.

The checked-in launcher and bootstrap files are retained for source review and
controlled testing, not as a supported installation path. The launcher accepts
only the exact owner-controlled, non-symlinked, non-group/world-writable hook at
`$CLAUDE_PLUGIN_DATA/venv/bin/forecost-hook`; it never falls back to `PATH`.
Runtime package bootstrapping is disabled. A future release still needs a
reviewed hash-locked offline installer, atomic rollback, and clean-host tests.
These checks narrow accidental and path-substitution failures; they do not
authenticate code against an agent or process that already has the same OS-user
privileges and can replace both the executable and local state.

For controlled development only, start in the reviewed local 0.3 checkout (the
public `main` branch is legacy), create a new isolated virtual environment, run
`python -m pip install -e .`, and inspect
`forecost setup claude --dry-run`. Do not apply the hook changes to a production
profile until the blockers in `docs/status.md` are cleared.

## Budget policy

Put budget rules in `~/.forecost/policy.toml` (the **home** policy always governs):

```toml
[[policy.rules]]
id = "weekly-cap"
scope = "week"       # session | day | week | month  (run is intentionally unsupported)
currency = "USD"
soft_limit = 50.0    # warn
hard_limit = 100.0   # deny
action = "deny"
```

A repo-local `.forecost.toml` is **not** trusted for enforcement by default (a
cloned repo could otherwise gate your session). Opt in per-machine with
`FORECOST_TRUST_PROJECT_POLICY=1`.

## Hook shape (source reference, not installation guidance)

The following shows the intended event coverage for reviewers. Do not paste it
into a production Claude profile while the release hold is active. Any eventual
manual configuration must point at an exact, approved executable from the
reviewed checkout:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath session-start", "timeout": 10 } ] }
    ],
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath prompt-submit", "timeout": 10 } ] }
    ],
    "PreToolUse": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath pre-tool", "timeout": 5 } ] }
    ],
    "PostToolUse": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath lifecycle", "timeout": 5, "async": true } ] }
    ],
    "PostToolUseFailure": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath lifecycle", "timeout": 5, "async": true } ] }
    ],
    "SubagentStart": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath lifecycle", "timeout": 5, "async": true } ] }
    ],
    "SubagentStop": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath lifecycle", "timeout": 5, "async": true } ] }
    ],
    "StopFailure": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath lifecycle", "timeout": 5, "async": true } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath stop", "timeout": 30, "async": true } ] }
    ],
    "SessionEnd": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath session-end", "timeout": 5 } ] }
    ]
  }
}
```

Run `forecost doctor` any time to see where data lives and what's set up.
