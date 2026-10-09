# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| Production release | **None currently** |
| Published v0.1.1 legacy forecaster | Unsupported; private reports still accepted best effort |
| Unreleased 0.3 / `main` | Best-effort research and controlled-trial review only |

## Reporting a Vulnerability

If you discover a security issue, please report it privately:

- Open a **private security advisory** on GitHub for this repository, or
- Email the maintainer listed in the project profile.

Please do **not** open a public issue for a vulnerability and do not attach a
real transcript, ledger database, policy file, API key, or absolute workspace
path. A synthetic reproducer is strongly preferred.

Please include:

- A clear description of the issue
- Steps to reproduce
- Potential impact
- Suggested remediation (if available)

## Response Process

The project currently has no founder-approved, staffed security-response SLA for
the unreleased 0.3 line. The following is the intended process, not a guaranteed
response time, until a named maintainer and support window are published:

1. We acknowledge reports as maintainer availability permits.
2. We validate and triage severity.
3. We prepare and test a fix.
4. We publish a patched release and disclose details responsibly.

## Scope

This policy applies to:

- The `forecost` Python package
- CLI entrypoints, local databases, recovery files, and destructive commands
- Claude Code plugin hooks and the LiteLLM callback
- Repository CI/package-release workflows and the proposed user-facing Action
  once it exists

The former `init --smart` upload path has been removed and is not a supported
interface. Reports about residual or accidentally reachable network-assisted
legacy scope-analysis code remain in scope, as do any regressions that could
send content from the current receipt product.
