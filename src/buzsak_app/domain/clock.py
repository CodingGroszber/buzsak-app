"""Injectable clock so time logic is testable (TST-04)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of wall-clock and monotonic time."""

    def now(self) -> datetime:
        """Current time, timezone-aware UTC (server timestamps are UTC, DATA-06)."""
        ...

    def monotonic(self) -> float:
        """Seconds from an arbitrary origin; for durations, never for display."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
