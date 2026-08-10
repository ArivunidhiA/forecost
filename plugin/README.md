# forecost — Claude Code plugin

Runs Forecost's experimental fail-open hooks inside Claude Code. The hooks append
content-free local observations, evaluate local policy when evidence is healthy,
and accrue a shadow calibration record. Missing, stale, or broken observation
degrades to no Forecost decision; it never claims provider-side containment.

## What it wires

| Hook event | What forecost does |
|---|---|
| `SessionStart` | Attempts to register an observed session/workspace using the explicitly installed `forecost-hook`. |
| `UserPromptSubmit` | Records a shadow estimate and may return a local policy decision when its evidence is healthy. |
| `PreToolUse` (all tool/MCP surfaces) | Performs the cached O(1) local policy check; `ask`/`deny` is neither distributed nor provider-side enforcement. |
| `PostToolUse` / `PostToolUseFailure` | Asynchronously records content-free tool lifecycle; `ExitPlanMode` and `Agent` retain structural kinds. |
| `SubagentStart` / `SubagentStop` / `StopFailure` | Asynchronously records the lifecycle event when Claude supplies it. |
| `Stop` | Asynchronously ingests the transcript delta, reconciles evidence, and updates the bounded post-turn summary. |
| `SessionEnd` | Synchronously writes only a tiny fsynced pending-settlement marker; idempotent reconciliation follows separately. |

The current capability boundary is published in `docs/capabilities.json`. Graph
identity is incomplete, provider-billed authority requires an offline export,
and maximum overrun is not bounded.

## Install (marketplace)

```
python3 -m pip install "forecost==0.3.0"
/plugin marketplace add ArivunidhiA/forecost
/plugin install forecost@forecost
```

Installation is deliberately explicit: no Claude lifecycle hook downloads or
executes packages. `scripts/run-hook.sh` first uses an existing isolated plugin
venv, then the `forecost-hook` on `PATH`, and otherwise exits successfully as a
no-op. `scripts/bootstrap.sh` remains an optional, manually invoked macOS/Linux
helper that installs exactly `forecost==0.3.0`; it is never run automatically.

The marketplace launcher currently supports macOS and Linux. Windows users
should use the manual installation below until a native launcher has passed the
same lifecycle tests.

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

## Manual install (no marketplace)

If you'd rather wire it by hand, add this to `~/.claude/settings.json`, pointing
at a Python that has forecost installed (`pip install -e .` from a clone):

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
