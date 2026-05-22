"""Voice-agent provider loader for telegramcaller."""
from __future__ import annotations
import os

from .base import Provider


def make_provider() -> Provider:
    kind = os.environ.get("VOICE_PROVIDER", "openai").lower()
    if kind in ("openai", "openai_realtime"):
        from .openai_realtime import OpenAIRealtimeProvider
        return OpenAIRealtimeProvider()
    raise SystemExit(
        f"Unknown VOICE_PROVIDER={kind!r}. "
        "Supported: openai."
    )


__all__ = ["Provider", "make_provider"]
