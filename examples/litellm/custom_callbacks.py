"""LiteLLM proxy callback wiring forecost into the gateway.

Drop this next to your LiteLLM `config.yaml` and reference it there:

    litellm_settings:
      callbacks: custom_callbacks.proxy_handler_instance

The pre-call hook enforces your ~/.forecost/policy.toml budget. Interactive
deployments fail open by default. A protected CI/gateway boundary can opt into
fail-closed behavior with ``ForecostLogger(ci_fail_closed=True)``; that explicit
constructor setting still applies when the policy file is missing, corrupt, or
unreadable. The success hook records each completed call as local evidence with
LiteLLM's own declared cost figure.
"""

from forecost.adapters.litellm_hook import ForecostLogger

proxy_handler_instance = ForecostLogger()

# For a protected CI/gateway boundary whose operator accepts availability loss:
# proxy_handler_instance = ForecostLogger(ci_fail_closed=True)
