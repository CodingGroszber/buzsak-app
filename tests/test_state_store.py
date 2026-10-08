"""Store: immutable replacement, failure handling, listeners (ARC-06, UPD-05, UPD-06)."""

from __future__ import annotations

import pytest
from conftest import load_state_fixture

from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.state.connection import ConnectionStatus, age_s, is_overdue
from buzsak_app.state.store import AppState, Store


@pytest.fixture
def store(clock) -> Store:
    return Store(clock)


def _snap(name="normal"):
    return parse_snapshot(load_state_fixture(name))


def test_initial_state_is_connecting_with_nothing_received(store) -> None:
    assert store.state == AppState()
    assert store.state.connection is ConnectionStatus.CONNECTING
    assert store.state.snapshot is None


def test_apply_snapshot_goes_online_and_stamps_receipt_time(store, clock) -> None:
    clock.advance(10)
    snap = _snap()
    store.apply_snapshot(snap)
    assert store.state.snapshot is snap
    assert store.state.connection is ConnectionStatus.ONLINE
    assert store.state.error is None
    assert store.state.received_at == 10


def test_state_objects_are_replaced_not_mutated(store) -> None:
    before = store.state
    store.apply_snapshot(_snap())
    assert store.state is not before
    assert before.snapshot is None


def test_failure_keeps_the_last_snapshot_and_its_receipt_time(store, clock) -> None:
    snap = _snap()
    store.apply_snapshot(snap)
    received = store.state.received_at
    clock.advance(5)
    store.apply_failure(ConnectionStatus.OFFLINE, "server unreachable")
    assert store.state.snapshot is snap
    assert store.state.received_at == received
    assert store.state.connection is ConnectionStatus.OFFLINE
    assert store.state.error == "server unreachable"


def test_recovery_clears_the_error(store) -> None:
    store.apply_failure(ConnectionStatus.OFFLINE, "down")
    store.apply_snapshot(_snap())
    assert store.state.error is None
    assert store.state.connection is ConnectionStatus.ONLINE


def test_listeners_receive_state_and_diff(store) -> None:
    seen = []
    store.subscribe(lambda state, diff: seen.append((state, diff)))
    store.apply_snapshot(_snap())
    state, diff = seen[0]
    assert state is store.state
    assert diff.structure_changed

    store.apply_snapshot(_snap())  # identical content
    assert seen[1][1].is_empty


def test_failure_notifies_with_an_empty_diff(store) -> None:
    seen = []
    store.subscribe(lambda state, diff: seen.append(
        (state.connection, diff.is_empty)))
    store.apply_failure(ConnectionStatus.SERVER_UNHEALTHY, "HTTP 503")
    assert seen == [(ConnectionStatus.SERVER_UNHEALTHY, True)]


def test_unsubscribe_stops_notifications(store) -> None:
    seen = []
    unsubscribe = store.subscribe(lambda state, diff: seen.append(1))
    unsubscribe()
    unsubscribe()  # idempotent
    store.apply_snapshot(_snap())
    assert seen == []


def test_a_failing_listener_does_not_block_others_or_the_store(store) -> None:
    seen = []

    def broken(state, diff):
        raise RuntimeError("boom")

    store.subscribe(broken)
    store.subscribe(lambda state, diff: seen.append(state.connection))
    store.apply_snapshot(_snap())
    assert seen == [ConnectionStatus.ONLINE]
    assert store.state.snapshot is not None


def test_listener_may_unsubscribe_while_notified(store) -> None:
    calls = []

    def once(state, diff):
        calls.append(1)
        unsubscribe()

    unsubscribe = store.subscribe(once)
    store.apply_snapshot(_snap())
    store.apply_snapshot(_snap("degraded"))
    assert calls == [1]


class TestFreshness:
    def test_age(self) -> None:
        assert age_s(None, 100) is None
        assert age_s(90, 100) == 10
        assert age_s(100, 99) == 0  # never negative

    def test_overdue_after_three_intervals(self) -> None:
        # exactly 3 intervals
        assert not is_overdue(100, 106, poll_interval_s=2)
        assert is_overdue(100, 106.1, poll_interval_s=2)

    def test_never_received_is_not_overdue(self) -> None:
        assert not is_overdue(None, 1000, poll_interval_s=2)
