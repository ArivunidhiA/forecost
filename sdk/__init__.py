"""
LLMLab SDK — One-line LLM cost tracking and optimization.

Quick start:
    import openai
    from llmlab import patch
    patch(openai, proxy_key="llmlab_pk_xxx")

    # All calls now tracked through LLMLab
    client = openai.OpenAI()
    response = client.chat.completions.create(model="gpt-4o", ...)
"""

from .patch import patch, unpatch, set_tags, clear_tags, get_tags
from .tracker import track_cost, log_call, track
from .config import get_config, set_config

__version__ = "0.5.0"

__all__ = [
    "patch",
    "unpatch",
    "set_tags",
    "clear_tags",
    "get_tags",
    "track_cost",
    "log_call",
    "track",
    "get_config",
    "set_config",
]
