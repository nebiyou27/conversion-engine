"""Shared runtime helpers for logging and idempotency."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from storage import cache

_LOCK = threading.Lock()
_SEEN_KEYS: set[tuple[str, str]] = set()


def configure_logging() -> None:
    """Configure a simple operator-friendly logging format once per process."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    else:
        root.setLevel(level)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_key(*parts: Any) -> str:
    """Build a stable idempotency key from arbitrary values."""
    payload = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Write a compact structured log line."""
    rendered_fields = " ".join(
        f"{key}={json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)}"
        for key, value in sorted(fields.items())
    )
    message = event if not rendered_fields else f"{event} {rendered_fields}"
    logger.log(level, message)


def claim_once(namespace: str, key: str, *, payload: dict[str, Any] | None = None) -> bool:
    """Return True the first time a key is seen, False on replay."""
    with _LOCK:
        cache_dir_value = os.getenv("IDEMPOTENCY_CACHE_DIR", "").strip()
        cache_dir = Path(cache_dir_value) if cache_dir_value else None
        marker = (namespace, key)

        if marker in _SEEN_KEYS:
            return False

        if cache_dir is not None:
            existing = cache.get(namespace, key, cache_dir=cache_dir)
            if existing is not None:
                _SEEN_KEYS.add(marker)
                return False
            cache.put(
                namespace,
                key,
                {
                    "claimed_at": utc_now(),
                    "payload": payload or {},
                },
                cache_dir=cache_dir,
            )

        _SEEN_KEYS.add(marker)
        return True
