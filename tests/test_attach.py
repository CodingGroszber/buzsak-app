"""Waiting for Flet to attach a service to the page (B-114)."""

from __future__ import annotations

import asyncio

from buzsak_app.ui.app import wait_until_attached


class _Service:
    """Raises like Flet's `page` property until `attach_after` accesses have happened."""

    def __init__(self, attach_after: int) -> None:
        self._left = attach_after
        self.accesses = 0

    @property
    def page(self):
        self.accesses += 1
        if self._left > 0:
            self._left -= 1
            raise RuntimeError("Control must be added to the page first")
        return object()


def test_returns_true_at_once_when_already_attached() -> None:
    service = _Service(attach_after=0)
    assert asyncio.run(wait_until_attached(service)) is True
    assert service.accesses == 1


def test_waits_until_the_service_is_attached() -> None:
    service = _Service(attach_after=3)
    assert asyncio.run(wait_until_attached(service, timeout_s=2)) is True
    assert service.accesses == 4


def test_gives_up_after_the_timeout_instead_of_hanging() -> None:
    service = _Service(attach_after=10**9)
    assert asyncio.run(wait_until_attached(service, timeout_s=0.2)) is False
