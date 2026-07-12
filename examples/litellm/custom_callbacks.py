"""LiteLLM proxy callback wiring forecost into the gateway.

Drop this next to your LiteLLM `config.yaml` and reference it there:

    litellm_settings:
      callbacks: custom_callbacks.proxy_handler_instance

The pre-call hook enforces your ~/.forecost/policy.toml budget (fail-open — a
forecost problem never takes down the gateway); the success hook records every
completed call into the local forecost ledger with LiteLLM's own cost figure.
"""

from forecost.adapters.litellm_hook import ForecostLogger

proxy_handler_instance = ForecostLogger()
