"""Polling: no overlap, backoff, pause/resume, error mapping (UPD-01..UPD-05, NFR-04)."""

from __future__ import annotations

import asyncio
import time

import pytest
from conftest import load_state_fixture

from buzsak_app.api.client import ConnectionFailed, HttpStatusError, MalformedResponse, Unauthorized
from buzsak_app.state.connection import ConnectionStatus
from buzsak_app.state.poller import Poller, backoff_delay_s
from buzsak_app.state.store import Store


async def _until(predicate, timeout=2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.001)


async def _settle() -> None:
    """Let a few loop iterations run so a wrongly-triggered poll would show up."""
    await asyncio.sleep(0.05)


class Fetcher:
    """Controllable stand-in for ServerClient.fetch_state."""

    def __init__(self) -> None:
        self.calls = 0
        self.inflight = 0
        self.max_inflight = 0
        self.gate: asyncio.Event | None = None
        self.error: BaseException | None = None
        self.payload = load_state_fixture("normal")

    async def __call__(self):
        self.calls += 1
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            if self.gate is not None:
                await self.gate.wait()
            if self.error is not None:
                raise self.error
            return self.payload
        finally:
            self.inflight -= 1


@pytest.fixture
def fetcher() -> Fetcher:
    return Fetcher()


def _poller(fetcher, clock, **kwargs) -> tuple[Poller, Store]:
    store = Store(clock)
    return Poller(fetcher, store, interval_s=kwargs.pop("interval_s", 1000), **kwargs), store


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=10))


class TestBackoffDelay:
    @pytest.mark.parametrize(
        ("failures", "expected"),
        [(0, 2), (1, 4), (2, 8), (3, 16), (4, 30),
         (5, 30), (50, 30), (100000, 30)],
    )
    def test_doubles_then_caps(self, failures, expected) -> None:
        assert backoff_delay_s(2, failures) == expected

    def test_never_below_the_interval_even_if_cap_is_lower(self) -> None:
        assert backoff_delay_s(30, 3) == 30
        assert backoff_delay_s(10, 1, cap_s=5) == 10

    def test_custom_cap(self) -> None:
        assert backoff_delay_s(1, 10, cap_s=8) == 8


class TestPollOnce:
    def test_success_updates_the_store_and_resets_failures(self, fetcher, clock) -> None:
        poller, store = _poller(fetcher, clock)
        fetcher.error = ConnectionFailed("server unreachable")
        assert _run(poller.poll_once()) is False
        assert poller.consecutive_failures == 1
        fetcher.error = None
        assert _run(poller.poll_once()) is True
        assert poller.consecutive_failures == 0
        assert store.state.connection is ConnectionStatus.ONLINE
        assert store.state.snapshot is not None

    @pytest.mark.parametrize(
        ("error", "status", "message"),
        [
            (ConnectionFailed("server unreachable"),
             ConnectionStatus.OFFLINE, "server unreachable"),
            (HttpStatusError(503), ConnectionStatus.SERVER_UNHEALTHY,
             "server returned HTTP 503"),
            (Unauthorized(401), ConnectionStatus.UNAUTHORIZED,
             "access token missing or invalid"),
            (Unauthorized(403), ConnectionStatus.UNAUTHORIZED,
             "access token rejected"),
            (MalformedResponse("response is not valid JSON"), ConnectionStatus.SERVER_UNHEALTHY,
             "response is not valid JSON"),
        ],
    )
    def test_api_errors_map_to_connection_status(self, fetcher, clock, error, status, message) -> None:
        poller, store = _poller(fetcher, clock)
        fetcher.error = error
        _run(poller.poll_once())
        assert store.state.connection is status
        assert store.state.error == message

    def test_unusable_snapshot_is_server_unhealthy_and_keeps_previous_data(self, fetcher, clock) -> None:
        poller, store = _poller(fetcher, clock)
        _run(poller.poll_once())
        good = store.state.snapshot
        fetcher.payload = {"generated_at": "never", "parties": []}
        assert _run(poller.poll_once()) is False
        assert store.state.connection is ConnectionStatus.SERVER_UNHEALTHY
        assert "unusable response" in store.state.error
        assert store.state.snapshot is good

    def test_unexpected_exception_is_contained_and_not_echoed(self, fetcher, clock) -> None:
        poller, store = _poller(fetcher, clock)
        fetcher.error = RuntimeError("secret token abc123 in message")
        assert _run(poller.poll_once()) is False
        assert store.state.error == "unexpected error"
        assert "abc123" not in store.state.error

    def test_tolerated_snapshot_issues_still_produce_a_snapshot(self, fetcher, clock) -> None:
        poller, store = _poller(fetcher, clock)
        fetcher.payload["parties"][0]["devices"].append({"label": "no id"})
        assert _run(poller.poll_once()) is True
        assert store.state.snapshot.issues


class TestLoop:
    def test_polls_immediately_then_waits_for_the_interval(self, fetcher, clock) -> None:
        async def scenario():
            poller, store = _poller(fetcher, clock, interval_s=1000)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.calls == 1)
            await _settle()
            assert fetcher.calls == 1  # the interval is 1000 s
            poller.stop()
            await asyncio.wait_for(task, 1)
            assert store.state.snapshot is not None

        _run(scenario())

    def test_polls_repeatedly_at_a_short_interval(self, fetcher, clock) -> None:
        async def scenario():
            poller, _ = _poller(fetcher, clock, interval_s=0.01)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.calls >= 3)
            poller.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_poll_now_triggers_an_immediate_extra_poll(self, fetcher, clock) -> None:
        async def scenario():
            poller, _ = _poller(fetcher, clock, interval_s=1000)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.calls == 1)
            poller.poll_now()
            await _until(lambda: fetcher.calls == 2)
            poller.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_polls_never_overlap_even_when_requested_during_a_fetch(self, fetcher, clock) -> None:
        async def scenario():
            fetcher.gate = asyncio.Event()
            poller, _ = _poller(fetcher, clock, interval_s=1000)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.calls == 1)
            for _ in range(5):
                poller.poll_now()
            await _settle()
            assert fetcher.calls == 1 and fetcher.inflight == 1
            fetcher.gate.set()
            # the requests collapse into one extra poll
            await _until(lambda: fetcher.calls == 2)
            await _settle()
            assert fetcher.calls == 2
            assert fetcher.max_inflight == 1
            poller.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_pause_stops_polling_and_resume_polls_at_once(self, fetcher, clock) -> None:
        async def scenario():
            poller, _ = _poller(fetcher, clock, interval_s=0.01)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.calls >= 1)
            poller.pause()
            await _settle()
            frozen = fetcher.calls
            await _settle()
            assert fetcher.calls == frozen
            assert poller.paused

            poller.poll_now()  # a manual refresh must not bypass the pause
            await _settle()
            assert fetcher.calls == frozen

            poller.resume()
            await _until(lambda: fetcher.calls > frozen)
            poller.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_resume_does_not_wait_out_a_long_interval(self, fetcher, clock) -> None:
        async def scenario():
            poller, _ = _poller(fetcher, clock, interval_s=1000)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.calls == 1)
            poller.pause()
            poller.resume()
            await _until(lambda: fetcher.calls == 2)
            poller.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_pause_during_a_fetch_lets_it_finish_but_starts_no_new_one(self, fetcher, clock) -> None:
        async def scenario():
            fetcher.gate = asyncio.Event()
            poller, store = _poller(fetcher, clock, interval_s=0.01)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.inflight == 1)
            poller.pause()
            fetcher.gate.set()
            await _until(lambda: store.state.snapshot is not None)
            await _settle()
            assert fetcher.calls == 1
            poller.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_stop_interrupts_the_wait_and_while_paused(self, fetcher, clock) -> None:
        async def scenario():
            poller, _ = _poller(fetcher, clock, interval_s=1000)
            task = asyncio.create_task(poller.run())
            await _until(lambda: fetcher.calls == 1)
            poller.stop()
            await asyncio.wait_for(task, 1)

            paused, _ = _poller(fetcher, clock, interval_s=1000)
            paused.pause()
            task = asyncio.create_task(paused.run())
            await _settle()
            paused.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_stop_before_run_never_fetches(self, fetcher, clock) -> None:
        async def scenario():
            poller, _ = _poller(fetcher, clock)
            poller.stop()
            await asyncio.wait_for(poller.run(), 1)
            assert fetcher.calls == 0

        _run(scenario())

    def test_keeps_running_through_failures_and_recovers(self, fetcher, clock) -> None:
        async def scenario():
            poller, store = _poller(
                fetcher, clock, interval_s=0.01, max_backoff_s=0.02)
            fetcher.error = ConnectionFailed("server unreachable")
            task = asyncio.create_task(poller.run())
            await _until(lambda: poller.consecutive_failures >= 2)
            assert store.state.connection is ConnectionStatus.OFFLINE
            fetcher.error = None
            await _until(lambda: store.state.connection is ConnectionStatus.ONLINE)
            assert poller.consecutive_failures == 0
            poller.stop()
            await asyncio.wait_for(task, 1)

        _run(scenario())

    def test_rejects_a_non_positive_interval(self, fetcher, clock) -> None:
        with pytest.raises(ValueError):
            Poller(fetcher, Store(clock), interval_s=0)
