"""
LLMLab - Cost tracking and optimization for LLM applications
"""

__version__ = "0.1.0"
__author__ = "LLMLab Team"

try:
    from llmlab.sdk.tracker import track_cost, log_call, track
    from llmlab.sdk.config import get_config, set_config

    __all__ = [
        "track_cost",
        "log_call",
        "track",
        "get_config",
        "set_config",
    ]
except ImportError:
    # SDK not installed (e.g. running backend tests standalone)
    __all__ = []
