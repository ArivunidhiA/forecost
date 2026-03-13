__version__ = "0.1.0"

__all__ = [
    "auto_track",
    "track_cost",
    "track",
    "log_call",
    "get_session_summary",
    "__version__",
]


def __getattr__(name):
    if name == "auto_track":
        from llmlab.interceptor import install

        return install
    if name == "track_cost":
        from llmlab.tracker import track_cost

        return track_cost
    if name == "track":
        from llmlab.tracker import track

        return track
    if name == "log_call":
        from llmlab.tracker import log_call

        return log_call
    if name == "get_session_summary":
        from llmlab.tracker import get_session_summary

        return get_session_summary
    raise AttributeError(f"module 'llmlab' has no attribute {name}")
