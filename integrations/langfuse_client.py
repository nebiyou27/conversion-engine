"""Langfuse tracing wrapper. Every LLM call and agent action logs through here."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    from langfuse import Langfuse
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    Langfuse = None  # type: ignore[assignment]


@dataclass
class _NoopGeneration:
    def generation(self, *args, **kwargs):
        return None


class _NoopClient:
    def trace(self, *args, **kwargs):
        return _NoopGeneration()

    def flush(self):
        return None


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    if Langfuse is None:
        logger.info("langfuse_unavailable using_noop_client=true")
        _client = _NoopClient()
        return _client

    _client = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )
    return _client


def trace(name: str, input: dict | None = None, metadata: dict | None = None):
    return _get_client().trace(name=name, input=input, metadata=metadata)


def flush():
    return _get_client().flush()
