"""Presentation catalog, labels and number display (SSOT-07, DATA-03, UX-10, UX-20)."""

from __future__ import annotations

import pytest
from conftest import load_state_fixture

from buzsak_app.domain.models import Parameter, ValueState
from buzsak_app.domain.presentation import (
    GENERIC,
    display_number,
    known_parameter_ids,
    presentation_for,
)
from buzsak_app.domain.snapshot import parse_snapshot
from buzsak_app.ui import strings


def _param(parameter_id="x", value=None, unit=None, state=ValueState.GOOD) -> Parameter:
    return Parameter(
        id=parameter_id, category="continuous", unit=unit, value=value, value_type=None,
        state=state, observed_at=None, last_changed_at=None, revision=0,
    )


def test_every_parameter_in_the_server_catalog_has_presentation_and_label() -> None:
    snap = parse_snapshot(load_state_fixture("normal"))
    ids = {p.id for party in snap.parties for d in party.devices for p in d.parameters}
    assert ids <= known_parameter_ids()
    assert ids <= set(strings.PARAMETER_LABELS)


def test_catalog_and_labels_cover_the_same_ids() -> None:
    assert known_parameter_ids() == set(strings.PARAMETER_LABELS)


def test_unknown_id_uses_generic_fallback() -> None:
    assert presentation_for("brand_new_kpi") is GENERIC
    assert strings.parameter_label("brand_new_kpi") == "Brand new kpi"
    assert strings.parameter_caption("brand_new_kpi") is None


def test_known_label_and_caption() -> None:
    assert strings.parameter_label("pressure_bar") == "Pressure"
    assert strings.parameter_caption("pressure_bar")


@pytest.mark.parametrize(
    ("parameter_id", "value", "unit", "text", "shown_unit"),
    [
        ("pressure_bar", 2.8, "bar", "2.80", "bar"),
        ("sensor_a_temperature_c", 21.64, "°C", "21.6", "°C"),
        ("water_level_liters", 640.0, "L", "640", "L"),
        ("automation_period_s", 600, "s", "600", "s"),
        ("automation_duty", 0.4, "ratio", "40", "%"),
        ("automation_duty", 1.0, "ratio", "100", "%"),
        # unknown id: float default, 1 decimal
        ("flow_lpm", 3.55, "L/min", "3.5", "L/min"),
        ("flow_count", 7, None, "7", None),
    ],
)
def test_display_number(parameter_id, value, unit, text, shown_unit) -> None:
    shown = display_number(_param(parameter_id, value, unit))
    assert (shown.text, shown.unit) == (text, shown_unit)


def test_zero_is_displayed_not_hidden() -> None:
    assert display_number(_param("automation_duty", 0.0, "ratio")).text == "0"


@pytest.mark.parametrize("value", [None, True, False, "manual"])
def test_display_number_is_none_for_non_numeric(value) -> None:
    assert display_number(_param("mode", value)) is None
