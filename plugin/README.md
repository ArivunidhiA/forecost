# forecost — Claude Code plugin

Runs forecost's fail-open hooks inside Claude Code: it records every turn into your
local, content-free ledger, gates budgets, and (in shadow mode) accrues the
calibration record. A forecost failure can never block Claude Code — every hook
exits 0 on error.

## What it wires

| Hook event | What forecost does |
|---|---|
| `SessionStart` | Registers the session/workspace using the explicitly installed `forecost-hook`. |
| `UserPromptSubmit` | Classifies the turn, records a shadow estimate, evaluates budget policy (can `block` on a hard cap). |
| `PreToolUse` (Task/Bash/WebFetch/WebSearch) | Cheap budget check; `ask`/`deny` only on an explicit, healthy policy decision. |
| `Stop` / `SessionEnd` | Ingests the transcript delta, reconciles estimates, logs the shadow guard. |

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
      { "matcher": "Task|Bash|WebFetch|WebSearch", "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath pre-tool", "timeout": 5 } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "/path/to/venv/bin/python -m forecost.hooks.fastpath stop", "timeout": 30, "async": true } ] }
    ]
  }
}
```

Run `forecost doctor` any time to see where data lives and what's set up.
