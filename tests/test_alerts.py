"""Synthetic alert evaluation and session lifecycle checks; no hardware (NTF-02..NTF-11)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from conftest import load_state_fixture

from buzsak_app.domain.alerts import (
    AlertRule, Comparison, Constant, Truth, ValueReference, evaluate,
)
from buzsak_app.domain.models import ValueState
from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.state.alert_monitor import AlertMonitor
from buzsak_app.state.alert_repository import AlertRepository, RULES_KEY, decode_rules
from buzsak_app.state.alert_session import AlertSession
from buzsak_app.ui import strings


def snapshot(value=31.0, state=ValueState.GOOD):
    source = parse_snapshot(load_state_fixture("normal"))
    device = source.parties[1].devices[0]
    parameter = replace(
        device.parameters[0], id="temperature", value=value,
        value_type="float", unit="C", state=state,
    )
    device = replace(device, parameters=(parameter,))
    return replace(source, parties=(replace(source.parties[1], devices=(device,)),))


def rule(rule_id="heat", threshold=30.0, name="Heat notice"):
    return AlertRule(rule_id, name, (Comparison(
        ValueReference("valve-controller", "temperature", "C"),
        ">=", Constant(threshold, "C"),
    ),))


@pytest.mark.parametrize("relation,expected", [
    ("<", False), ("<=", True), (">", False), (">=", True),
    ("==", True), ("!=", False),
])
def test_numeric_relations(relation, expected):
    original = rule()
    comparison = replace(original.comparisons[0], relation=relation)
    result = evaluate(
        replace(original, comparisons=(comparison,)), snapshot(30))
    assert result is (Truth.TRUE if expected else Truth.FALSE)


@pytest.mark.parametrize("state", [
    ValueState.STALE, ValueState.INVALID, ValueState.UNAVAILABLE, ValueState.NO_DATA,
])
def test_untrusted_parameter_is_unknown(state):
    assert evaluate(rule(), snapshot(state=state)) is Truth.UNKNOWN


@pytest.mark.parametrize("value", [True, "31", None, float("nan"), float("inf")])
def test_non_numeric_values_are_unknown(value):
    assert evaluate(rule(), snapshot(value)) is Truth.UNKNOWN


@pytest.mark.parametrize("connective", ["AND", "OR"])
def test_unknown_dominates_every_connective(connective):
    original = rule()
    missing = replace(
        original.comparisons[0], left=ValueReference("missing", "x", "C"))
    for value in (0, 31):
        combined = replace(
            original, comparisons=original.comparisons + (missing,), connective=connective)
        assert evaluate(combined, snapshot(value)) is Truth.UNKNOWN


def test_units_constant_only_and_invalid_operators_are_rejected():
    reference = ValueReference("device", "temperature", "C")
    with pytest.raises(ValueError):
        Comparison(reference, ">", Constant(30, "%"))
    with pytest.raises(ValueError):
        Comparison(Constant(1, "C"), ">", Constant(0, "C"))
    with pytest.raises(ValueError):
        Comparison(reference, "=!", Constant(30, "C"))
    with pytest.raises(ValueError):
        ValueReference("device", "x", "")
    with pytest.raises(ValueError):
        Constant(float("nan"), "C")


def monitor(clock, rules=None):
    result = AlertMonitor(clock)
    result.set_rules(rules or (rule(),))
    result.start()
    return result


def test_startup_continuous_true_and_rearm(clock):
    engine = monitor(clock)
    assert engine.evaluate_snapshot(snapshot()) == (rule(),)
    clock.advance(10)
    assert engine.evaluate_snapshot(snapshot()) == ()
    assert engine.evaluate_snapshot(snapshot(20)) == ()
    assert engine.evaluate_snapshot(snapshot()) == (rule(),)


def test_cooldown_edge_is_discarded_not_delayed(clock):
    engine = monitor(clock)
    assert engine.evaluate_snapshot(snapshot())
    clock.advance(1)
    engine.evaluate_snapshot(snapshot(20))
    assert engine.evaluate_snapshot(snapshot()) == ()
    clock.advance(9)
    assert engine.evaluate_snapshot(snapshot()) == ()
    engine.evaluate_snapshot(snapshot(20))
    assert engine.evaluate_snapshot(snapshot())


def test_unknown_and_network_failure_do_not_rearm(clock):
    engine = monitor(clock)
    assert engine.evaluate_snapshot(snapshot())
    clock.advance(20)
    engine.evaluate_snapshot(snapshot(20), trustworthy=False)
    engine.evaluate_snapshot(snapshot(state=ValueState.STALE))
    assert engine.evaluate_snapshot(snapshot()) == ()


def test_simultaneous_rules_have_independent_cooldowns(clock):
    engine = monitor(clock, (rule("a"), rule("b")))
    assert [item.id for item in engine.evaluate_snapshot(snapshot())] == [
        "a", "b"]
    engine.set_rules((rule("a"), rule("b"), rule("c")))
    assert [item.id for item in engine.evaluate_snapshot(snapshot())] == ["c"]


def test_edits_keep_cooldown_and_rename_preserves_truth(clock):
    engine = monitor(clock)
    assert engine.evaluate_snapshot(snapshot())
    clock.advance(10)
    engine.set_rules((rule(name="Renamed"),))
    assert engine.evaluate_snapshot(snapshot()) == ()
    engine.set_rules((rule(threshold=25),))
    assert engine.evaluate_snapshot(snapshot())
    engine.set_rules((rule(threshold=24),))
    assert engine.evaluate_snapshot(snapshot()) == ()
    clock.advance(10)
    assert engine.evaluate_snapshot(snapshot()) == ()


def test_stop_preserves_definitions_and_restart_resets_session(clock):
    engine = monitor(clock)
    assert engine.evaluate_snapshot(snapshot())
    engine.stop()
    assert engine.evaluate_snapshot(snapshot()) == ()
    engine.start()
    assert engine.evaluate_snapshot(snapshot())


def test_rules_roundtrip_with_unicode_and_no_session_state():
    class Store:
        data = {}

        async def get(self, key):
            return self.data.get(key)

        async def set(self, key, value):
            self.data[key] = value
            return True

    store = Store()
    repository = AlertRepository(store)
    original = (rule(name="Heat \U0001f321 notice"),)
    assert asyncio.run(repository.save(original))
    assert asyncio.run(repository.load()) == original
    payload = json.loads(store.data[RULES_KEY])
    assert set(payload) == {"version", "rules"}
    assert set(payload["rules"][0]) == {
        "id", "name", "comparisons", "connective"}


@pytest.mark.parametrize("raw", [None, [], {}, {"version": 2, "rules": []},
                                 {"version": True, "rules": []},
                                 {"version": 1, "rules": [None]}])
def test_corrupt_rule_payloads_are_rejected(raw):
    with pytest.raises(ValueError):
        decode_rules(raw)


def test_rule_storage_failure_does_not_claim_success(caplog):
    class Store:
        async def set(self, key, value):
            raise OSError("sensitive storage failure details")

    assert asyncio.run(AlertRepository(Store()).save((rule(),))) is False
    assert "sensitive" not in caplog.text


def test_editor_saves_single_comparison_through_the_cascaded_picker():
    from buzsak_app.ui.alert_editor import AlertEditor

    saved = []

    async def save(items):
        saved.append(items)
        return True

    editor = AlertEditor(on_save=save)
    editor.refresh(snapshot())
    editor.new(None)
    picker = editor.picker
    location = next(iter(editor.tree))
    picker.location.value = location
    picker._populate_category(keep_value=False)
    category = next(iter(editor.tree[location]))
    picker.category.value = category
    picker._populate_sensor(keep_value=False)
    editor.name.value = "Heat \U0001f321 notice"
    picker.relation.value = ">="
    picker.constant.value = "30"
    asyncio.run(editor.save(None))
    assert len(saved) == 1
    assert saved[0][0].name == editor.name.value
    assert len(saved[0][0].comparisons) == 1
    assert evaluate(saved[0][0], snapshot()) is Truth.TRUE
    assert editor._list_container.visible and not editor._form_container.visible


def test_editor_rejects_an_incomplete_selection():
    from buzsak_app.ui.alert_editor import AlertEditor

    async def save(items):
        return True

    editor = AlertEditor(on_save=save)
    editor.refresh(snapshot())
    editor.new(None)
    editor.name.value = "Heat"
    asyncio.run(editor.save(None))
    assert editor.rules == ()
    assert editor.message.value == strings.ALERT_INVALID


def test_editor_preserves_identity_when_renaming():
    from buzsak_app.ui.alert_editor import AlertEditor

    async def save(items):
        return True

    editor = AlertEditor(on_save=save)
    editor.refresh(snapshot())
    editor.new(None)
    picker = editor.picker
    location = next(iter(editor.tree))
    picker.location.value = location
    picker._populate_category(keep_value=False)
    category = next(iter(editor.tree[location]))
    picker.category.value = category
    picker._populate_sensor(keep_value=False)
    editor.name.value = "Heat"
    picker.constant.value = "30"
    asyncio.run(editor.save(None))
    identifier = editor.rules[0].id

    edit = editor._list.controls[0].controls[1].on_click
    edit(None)
    assert editor._form_container.visible
    editor.name.value = "Renamed"
    asyncio.run(editor.save(None))
    assert len(editor.rules) == 1 and editor.rules[0].id == identifier
    assert editor.rules[0].name == "Renamed"


class FakeNotifications:
    def __init__(self):
        self.started = False
        self.allowed = True
        self.messages = []
        self.reason = "stopped"

    def start(self):
        self.started = True
        self.reason = "active"
        return True

    def stop(self):
        self.started = False
        self.reason = "stopped"

    def active(self):
        return self.started

    def status(self):
        return self.reason

    def permission_granted(self):
        return self.allowed

    def notify(self, name):
        if self.allowed:
            self.messages.append(name)
        return self.allowed


def test_authenticated_session_delivers_simultaneous_rules_and_stops_on_auth_loss(clock):
    bridge = FakeNotifications()
    session = AlertSession(clock, bridge)
    session.set_rules((rule("a", name="First"), rule("b", name="Second")))
    assert session.process(snapshot(), authenticated=False, trusted=True) == ()
    assert bridge.messages == []
    session.process(snapshot(), authenticated=True, trusted=True)
    assert bridge.messages == ["First", "Second"]
    assert session.running
    session.process(None, authenticated=False, trusted=False)
    assert not session.running and not bridge.active()
    assert len(session.rules) == 2


def test_denied_permission_consumes_trigger_without_catchup(clock):
    bridge = FakeNotifications()
    bridge.allowed = False
    session = AlertSession(clock, bridge)
    session.set_rules((rule(),))
    assert session.process(snapshot(), authenticated=True, trusted=True)
    assert session.running and bridge.messages == []
    bridge.allowed = True
    clock.advance(10)
    assert session.process(snapshot(), authenticated=True, trusted=True) == ()
    session.process(snapshot(20), authenticated=True, trusted=True)
    session.process(snapshot(), authenticated=True, trusted=True)
    assert bridge.messages == [rule().name]


def test_timeout_blocks_automatic_restart_until_foreground_return(clock):
    bridge = FakeNotifications()
    session = AlertSession(clock, bridge)
    session.set_rules((rule(),))
    session.process(snapshot(), authenticated=True, trusted=True)
    bridge.started = False
    bridge.reason = "timeout"
    session.check_service()
    assert not session.running and session.blocked
    assert session.process(snapshot(), authenticated=True, trusted=True) == ()
    assert not bridge.started
    session.foreground()
    assert session.process(snapshot(), authenticated=True, trusted=True)


def test_network_failure_does_not_stop_service_or_rearm(clock):
    bridge = FakeNotifications()
    session = AlertSession(clock, bridge)
    session.set_rules((rule(),))
    session.process(snapshot(), authenticated=True, trusted=True)
    clock.advance(10)
    session.process(snapshot(20), authenticated=True, trusted=False)
    assert session.running
    assert session.process(snapshot(), authenticated=True, trusted=True) == ()


@pytest.mark.parametrize("monitoring", [False, True])
def test_runtime_keeps_active_monitoring_across_ui_detach(monitoring):
    from types import SimpleNamespace
    import flet as ft
    from buzsak_app.settings import Settings
    from buzsak_app.state.poller import Poller
    from buzsak_app.ui.runtime import Runtime

    class Page:
        def update(self):
            pass

    bridge = FakeNotifications()
    runtime = Runtime(Page(), None, Settings(token="test-token"),
                      alert_rules=(rule(),), notifications=bridge)
    if monitoring:
        runtime.alert_session.process(
            snapshot(), authenticated=True, trusted=True)
    runtime._poller = Poller(lambda: None, runtime.store, interval_s=2)
    runtime.on_lifecycle(SimpleNamespace(state=ft.AppLifecycleState.PAUSE))
    assert runtime._poller.paused is not monitoring
    assert not runtime.view.visible
    runtime.on_lifecycle(SimpleNamespace(state=ft.AppLifecycleState.DETACH))
    assert runtime._poller.paused is not monitoring
    assert runtime.alert_session.running is monitoring
    assert not runtime.view.visible
    runtime.on_lifecycle(SimpleNamespace(state=ft.AppLifecycleState.RESUME))
    assert not runtime._poller.paused
    assert runtime.view.visible


def test_android_reattach_preserves_poller_truth_and_cooldown():
    from buzsak_app.settings import Settings
    from buzsak_app.state.poller import Poller
    from buzsak_app.ui.runtime import Runtime

    class Page:
        def update(self):
            pass

    bridge = FakeNotifications()
    runtime = Runtime(Page(), None, Settings(token="test-token"),
                      alert_rules=(rule(),), notifications=bridge)
    runtime.alert_session.process(snapshot(), authenticated=True, trusted=True)
    poller = Poller(lambda: None, runtime.store, interval_s=2)
    runtime._poller = poller
    old_view = runtime.view
    runtime.reattach(Page(), None, None, None)
    assert runtime._poller is poller
    assert not old_view.visible
    assert runtime.view is not old_view and runtime.view.visible
    assert runtime.alert_session.running
    assert runtime.alert_session.process(
        snapshot(), authenticated=True, trusted=True) == ()
    assert bridge.messages == [rule().name]
