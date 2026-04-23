"""Small bounded retry helper for transient provider failures."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def retry_call(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay_seconds: float = 0.2,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    logger: logging.Logger | None = None,
    operation_name: str = "operation",
) -> T:
    """Run an operation with bounded exponential backoff."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    log = logger or logging.getLogger(__name__)
    last_exc: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt >= attempts:
                break

            delay = base_delay_seconds * (2 ** (attempt - 1))
            log.warning(
                "%s attempt %s/%s failed: %s; retrying in %.2fs",
                operation_name,
                attempt,
                attempts,
                exc,
                delay,
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc
