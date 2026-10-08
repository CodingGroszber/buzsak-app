"""Shared test fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_state_fixture(name: str) -> dict:
    """Synthetic `/api/dashboard/state` payload (TST-03)."""
    return json.loads((FIXTURES / "state" / f"{name}.json").read_text(encoding="utf-8"))


class FakeClock:
    """Manually advanced clock (TST-04)."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)
        self._mono = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._mono += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
