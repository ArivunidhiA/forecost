__version__ = "0.1.0"

__all__ = [
    "auto_track",
    "track_cost",
    "track",
    "log_call",
    "log_stream_usage",
    "get_session_summary",
    "get_interceptor_stats",
    "disable",
    "__version__",
]


def __getattr__(name: str):
    if name == "auto_track":
        from llmlab.tracker import auto_track

        return auto_track
    if name == "track_cost":
        from llmlab.tracker import track_cost

        return track_cost
    if name == "track":
        from llmlab.tracker import track

        return track
    if name == "log_call":
        from llmlab.tracker import log_call

        return log_call
    if name == "log_stream_usage":
        from llmlab.tracker import log_stream_usage

        return log_stream_usage
    if name == "get_session_summary":
        from llmlab.tracker import get_session_summary

        return get_session_summary
    if name == "get_interceptor_stats":
        from llmlab.interceptor import get_interceptor_stats

        return get_interceptor_stats
    if name == "disable":
        import os

        from llmlab.interceptor import uninstall

        def _disable() -> None:
            uninstall()
            os.environ["LLMLAB_DISABLED"] = "1"

        return _disable
    raise AttributeError(f"module 'llmlab' has no attribute {name}")
