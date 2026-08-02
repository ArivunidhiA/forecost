# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| Latest published release | Yes |
| `main` | Best effort; not a release |
| Older releases | No |

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

1. We acknowledge reports within 72 hours.
2. We validate and triage severity.
3. We prepare and test a fix.
4. We publish a patched release and disclose details responsibly.

## Scope

This policy applies to:

- The `forecost` Python package
- CLI entrypoints, local databases, recovery files, and destructive commands
- Claude Code plugin hooks and the LiteLLM callback
- Bundled GitHub Actions and package-release workflows

The legacy `init --smart` cloud-assisted scope analysis is opt-in and is not
part of the content-free ledger path. Security reports about its outbound-data
preview, prompt injection, or secret detection remain in scope.
