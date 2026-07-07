"""Small retry helper implementing the spec's 3-retry exponential backoff.

Kept dependency-free (a simple loop) to avoid pulling in `tenacity`.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default: retry on any network/HTTP error raised by `requests`.
DEFAULT_EXCEPTIONS: Tuple[Type[BaseException], ...] = (Exception,)


def with_retry(
    func: Callable[[], T],
    retries: int = 3,
    backoff_base: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = DEFAULT_EXCEPTIONS,
    label: str = "operation",
) -> T:
    """Call ``func`` up to ``retries`` times with exponential backoff.

    The first attempt counts as attempt 1, so ``retries=3`` means up to 3
    total calls (2 sleeps between them). Backoff is ``backoff_base * 2**(n-1)``
    seconds for attempt n (1s, 2s, ...).

    Sleeps are looked up via ``time.sleep`` at call time so tests can patch
    ``retry.time.sleep`` without re-binding a default argument.

    Raises the last exception if every attempt fails.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            return func()
        except exceptions as e:  # noqa: BLE001 - intentional broad capture
            last_exc = e
            if attempt == retries:
                break
            sleep_for = backoff_base * (2 ** (attempt - 1))
            logger.warning(
                "%s failed (attempt %d/%d): %s; retrying in %.1fs",
                label,
                attempt,
                retries,
                e,
                sleep_for,
            )
            time.sleep(sleep_for)
    assert last_exc is not None  # pragma: no cover - only reachable if retries < 1
    raise last_exc
