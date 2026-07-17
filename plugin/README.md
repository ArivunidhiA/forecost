# forecost — Claude Code plugin

Runs forecost's fail-open hooks inside Claude Code: it records every turn into your
local, content-free ledger, gates budgets, and (in shadow mode) accrues the
calibration record. A forecost failure can never block Claude Code — every hook
exits 0 on error.

## What it wires

| Hook event | What forecost does |
|---|---|
| `SessionStart` | Bootstraps a private venv (first run) and registers the session/workspace. |
| `UserPromptSubmit` | Classifies the turn, records a shadow estimate, evaluates budget policy (can `block` on a hard cap). |
| `PreToolUse` (Task/Bash/WebFetch/WebSearch) | Cheap budget check; `ask`/`deny` only on an explicit, healthy policy decision. |
| `Stop` / `SessionEnd` | Ingests the transcript delta, reconciles estimates, logs the shadow guard. |

## Install (marketplace)

```
/plugin marketplace add ArivunidhiA/forecost
/plugin install forecost@forecost
```

On first `SessionStart`, `scripts/bootstrap.sh` creates a venv in the plugin's
persistent data dir (`${CLAUDE_PLUGIN_DATA}/venv`) and installs forecost from git
(there is no PyPI release yet). Subsequent hooks reuse it. Requires `python3` (or
`uv`) on your `PATH`.

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
