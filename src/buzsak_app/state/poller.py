"""Polling service: sequential fetches, exponential backoff, pause and resume (UPD-01..UPD-05)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from buzsak_app.api.client import ApiError, ConnectionFailed, Unauthorized
from buzsak_app.domain.snapshot import SnapshotFormatError, parse_snapshot
from buzsak_app.settings import POLL_INTERVAL_MAX_S
from buzsak_app.state.connection import ConnectionStatus
from buzsak_app.state.store import Store

logger = logging.getLogger(__name__)

Fetch = Callable[[], Awaitable[dict[str, Any]]]


def backoff_delay_s(interval_s: float, consecutive_failures: int, cap_s: float = POLL_INTERVAL_MAX_S) -> float:
    """Wait before the next poll: the interval, doubled per consecutive failure, capped (UPD-05)."""
    if consecutive_failures <= 0:
        return interval_s
    # Cap the exponent: a long outage must not overflow the float multiplication.
    return max(interval_s, min(cap_s, interval_s * 2 ** min(consecutive_failures, 32)))


class Poller:
    """Runs one fetch at a time, so polls cannot overlap (UPD-04).

    `poll_now()` and `resume()` only wake the loop; they never fetch directly.
    Single use: once `stop()` has been called, create a new instance.
    """

    def __init__(
        self,
        fetch: Fetch,
        store: Store,
        *,
        interval_s: float,
        max_backoff_s: float = POLL_INTERVAL_MAX_S,
    ) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self._fetch = fetch
        self._store = store
        self.interval_s = interval_s
        self._max_backoff_s = max_backoff_s
        self._failures = 0
        self._stopping = False
        self._active = asyncio.Event()
        self._active.set()
        self._wake = asyncio.Event()

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    @property
    def paused(self) -> bool:
        return not self._active.is_set()

    def pause(self) -> None:
        """Stop polling while the app is in the background (UPD-03); an in-flight fetch finishes."""
        self._active.clear()

    def resume(self) -> None:
        """Poll again immediately (UPD-03)."""
        self._active.set()
        self._wake.set()

    def poll_now(self) -> None:
        """Ask for a fetch as soon as the current one, if any, finishes (UPD-02)."""
        self._wake.set()

    def stop(self) -> None:
        self._stopping = True
        self._active.set()
        self._wake.set()

    async def run(self) -> None:
        while not self._stopping:
            await self._active.wait()
            if self._stopping:
                break
            # Clear only now: requests made during the poll below must trigger another one.
            self._wake.clear()
            await self.poll_once()
            if self._stopping or self.paused:
                continue
            delay = backoff_delay_s(
                self.interval_s, self._failures, self._max_backoff_s)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def poll_once(self) -> bool:
        """One fetch; returns whether it produced a snapshot. Never raises (NFR-04)."""
        try:
            snapshot = parse_snapshot(await self._fetch())
        except ConnectionFailed as error:
            return self._fail(ConnectionStatus.OFFLINE, str(error))
        except Unauthorized as error:
            return self._fail(ConnectionStatus.UNAUTHORIZED, str(error))
        except ApiError as error:
            return self._fail(ConnectionStatus.SERVER_UNHEALTHY, str(error))
        except SnapshotFormatError as error:
            return self._fail(ConnectionStatus.SERVER_UNHEALTHY, f"unusable response: {error}")
        except Exception as error:
            # Log the type only: messages may echo server data (SEC-05).
            logger.warning("unexpected poll error: %s", type(error).__name__)
            return self._fail(ConnectionStatus.SERVER_UNHEALTHY, "unexpected error")

        self._failures = 0
        if snapshot.issues:
            logger.warning("snapshot had %d tolerated issue(s)",
                           len(snapshot.issues))
        self._store.apply_snapshot(snapshot)
        return True

    def _fail(self, status: ConnectionStatus, message: str) -> bool:
        self._failures += 1
        self._store.apply_failure(status, message)
        return False
