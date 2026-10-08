"""Connection status and data freshness, as pure functions of state and time (UPD-05, UPD-06)."""

from __future__ import annotations

from enum import StrEnum

# The "last updated" indicator warns when older than this many poll intervals (UPD-06).
OVERDUE_INTERVALS = 3


class ConnectionStatus(StrEnum):
    CONNECTING = "connecting"  # nothing received yet
    ONLINE = "online"
    OFFLINE = "offline"  # server unreachable or timed out
    # reachable but answering badly (HTTP error, bad body)
    SERVER_UNHEALTHY = "server_unhealthy"
    # reachable, but the token is missing or rejected (SRV-07)
    UNAUTHORIZED = "unauthorized"


def age_s(received_at: float | None, now: float) -> float | None:
    """Seconds since the last good snapshot; both values are monotonic readings."""
    return None if received_at is None else max(0.0, now - received_at)


def is_overdue(received_at: float | None, now: float, poll_interval_s: float) -> bool:
    """True when the data is older than `OVERDUE_INTERVALS` poll intervals.

    False when nothing was ever received: the connection status already says so.
    """
    age = age_s(received_at, now)
    return age is not None and age > OVERDUE_INTERVALS * poll_interval_s
