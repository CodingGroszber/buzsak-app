"""Detecting server data that is old although the server answers (DATA-02, UPD-06)."""

from __future__ import annotations

import copy
from dataclasses import replace

from conftest import load_state_fixture

from buzsak_app.domain.models import ValueState
from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.domain.staleness import stale_server_data_age_s


def _all_stale(payload: dict, observed_at: str = "2026-10-03T12:00:00Z") -> dict:
    payload = copy.deepcopy(payload)
    for party in payload["parties"]:
        for device in party["devices"]:
            for parameter in device["parameters"]:
                parameter.update(stale=True, observed_at=observed_at)
    return payload


def test_fresh_data_is_not_reported() -> None:
    assert stale_server_data_age_s(parse_snapshot(
        load_state_fixture("normal"))) is None


def test_no_snapshot_is_not_reported() -> None:
    assert stale_server_data_age_s(None) is None


def test_every_parameter_stale_reports_the_age_from_server_timestamps() -> None:
    snap = parse_snapshot(_all_stale(load_state_fixture("normal")))
    # generated 2026-10-05T12:00Z, observed 10-03
    assert stale_server_data_age_s(snap) == 2 * 86400


def test_the_newest_observation_defines_the_age() -> None:
    payload = _all_stale(load_state_fixture("normal"))
    payload["parties"][0]["devices"][0]["parameters"][0]["observed_at"] = "2026-10-05T11:00:00Z"
    assert stale_server_data_age_s(parse_snapshot(payload)) == 3600


def test_one_live_parameter_means_the_data_is_not_old() -> None:
    payload = _all_stale(load_state_fixture("normal"))
    payload["parties"][0]["devices"][0]["parameters"][0].update(stale=False)
    assert stale_server_data_age_s(parse_snapshot(payload)) is None


def test_mixed_stale_and_unavailable_is_left_to_device_health() -> None:
    assert stale_server_data_age_s(parse_snapshot(
        load_state_fixture("degraded"))) is None


def test_parameters_without_data_are_ignored() -> None:
    payload = _all_stale(load_state_fixture("normal"))
    payload["parties"][0]["devices"][0]["parameters"].append(
        {"id": "x", "category": "boolean", "unit": None, "value": None, "value_type": None,
         "quality": "unavailable", "stale": False, "observed_at": None, "last_changed_at": None,
         "revision": 0, "has_data": False}
    )
    assert stale_server_data_age_s(parse_snapshot(payload)) == 2 * 86400


def test_nothing_observed_is_not_reported() -> None:
    assert stale_server_data_age_s(parse_snapshot(
        load_state_fixture("matter_unconfigured"))) is None


def test_age_is_never_negative() -> None:
    snap = parse_snapshot(_all_stale(load_state_fixture(
        "normal"), observed_at="2026-10-05T13:00:00Z"))
    assert stale_server_data_age_s(snap) == 0.0


def test_a_parameter_with_a_missing_timestamp_yields_none_not_a_crash() -> None:
    snap = parse_snapshot(_all_stale(load_state_fixture("normal")))
    for party in snap.parties:
        for device in party.devices:
            assert all(p.state is ValueState.STALE for p in device.parameters)
    stripped = replace(snap, parties=tuple(
        replace(party, devices=tuple(
            replace(device, parameters=tuple(replace(p, observed_at=None)
                    for p in device.parameters))
            for device in party.devices))
        for party in snap.parties))
    assert stale_server_data_age_s(stripped) is None
