from __future__ import annotations

import os
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

try:
    from langfuse import get_client, observe
except Exception:  # pragma: no cover
    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func
        return decorator

    def get_client(*args: Any, **kwargs: Any):
        class _DummyClient:
            def update_current_trace(self, **kwargs: Any) -> None:
                return None

            def update_current_span(self, **kwargs: Any) -> None:
                return None

            def start_as_current_generation(self, *args: Any, **kwargs: Any):
                class _DummySpan:
                    def __enter__(self):
                        return self

                    def __exit__(self, exc_type, exc, tb):
                        return False

                    def update(self, **kwargs: Any) -> None:
                        return None

                return _DummySpan()

        return _DummyClient()


class _LangfuseContextProxy:
    def update_current_trace(self, **kwargs: Any) -> None:
        get_client().update_current_trace(**kwargs)

    def update_current_span(self, **kwargs: Any) -> None:
        usage_details = kwargs.pop("usage_details", None)
        if usage_details is not None:
            metadata = kwargs.get("metadata")
            if metadata is None:
                kwargs["metadata"] = {"usage_details": usage_details}
            elif isinstance(metadata, dict):
                kwargs["metadata"] = {**metadata, "usage_details": usage_details}
        get_client().update_current_span(**kwargs)

    def update_current_observation(self, **kwargs: Any) -> None:
        self.update_current_span(**kwargs)


langfuse_context = _LangfuseContextProxy()


def tracing_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
