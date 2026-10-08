"""Single source of UI-facing state: replaced immutably, listeners notified (ARC-06, UPD-07, SSOT-05).

Views read `Store.state` and subscribe; they never mutate it. A failed poll keeps the last
snapshot and only changes the connection status, so stale data stays visible but marked.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from buzsak_app.domain.clock import Clock
from buzsak_app.domain.models import Snapshot
from buzsak_app.state.connection import ConnectionStatus
from buzsak_app.state.diff import SnapshotDiff, diff_snapshots

logger = logging.getLogger(__name__)

_NO_CHANGE = SnapshotDiff(structure_changed=False, changed_devices=frozenset(
), changed_parameters=frozenset())
_RESET = SnapshotDiff(structure_changed=True, changed_devices=frozenset(
), changed_parameters=frozenset())


@dataclass(frozen=True)
class AppState:
    snapshot: Snapshot | None = None
    connection: ConnectionStatus = ConnectionStatus.CONNECTING
    # User-safe description of the last failure; None while online.
    error: str | None = None
    # Monotonic reading when `snapshot` arrived; basis for "updated N s ago" (UPD-06).
    received_at: float | None = None


Listener = Callable[[AppState, SnapshotDiff], None]


class Store:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._state = AppState()
        self._listeners: list[Listener] = []

    @property
    def state(self) -> AppState:
        return self._state

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register a listener; returns a function that removes it."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def apply_snapshot(self, snapshot: Snapshot) -> None:
        diff = diff_snapshots(self._state.snapshot, snapshot)
        self._state = AppState(
            snapshot=snapshot,
            connection=ConnectionStatus.ONLINE,
            error=None,
            received_at=self._clock.monotonic(),
        )
        self._notify(diff)

    def apply_failure(self, status: ConnectionStatus, message: str) -> None:
        """Record a failed poll; the previous snapshot is kept (UPD-05)."""
        self._state = replace(self._state, connection=status, error=message)
        self._notify(_NO_CHANGE)

    def reset(self) -> None:
        """Forget everything, e.g. after the server address changed: old data is not the new server's."""
        self._state = AppState()
        self._notify(_RESET)

    def _notify(self, diff: SnapshotDiff) -> None:
        for listener in list(self._listeners):
            try:
                listener(self._state, diff)
            except Exception:
                # One broken view must not stop polling (NFR-04).
                logger.exception("store listener failed")
