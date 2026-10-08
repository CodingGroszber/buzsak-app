"""Clock and settings basics (TST-04, ARC-09, SEC-03)."""

from __future__ import annotations

from datetime import UTC

import pytest

from buzsak_app.domain.clock import SystemClock
from buzsak_app.settings import DEFAULT_SERVER_URL, Settings


def test_fake_clock_advances_both_clocks(clock) -> None:
    start = clock.now()
    clock.advance(2.5)
    assert (clock.now() - start).total_seconds() == 2.5
    assert clock.monotonic() == 2.5


def test_system_clock_is_utc_aware() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_settings_defaults() -> None:
    s = Settings()
    assert s.server_url == DEFAULT_SERVER_URL == "https://192.168.1.95"
    assert s.poll_interval_s == 2.0


@pytest.mark.parametrize("interval", [0.5, 31.0])
def test_settings_reject_out_of_range_poll_interval(interval: float) -> None:
    with pytest.raises(ValueError):
        Settings(poll_interval_s=interval)


def test_settings_reject_non_http_url() -> None:
    with pytest.raises(ValueError):
        Settings(server_url="ftp://pi")


def test_settings_repr_hides_token() -> None:
    assert "s3cret" not in repr(Settings(token="s3cret"))
