"""Language-neutral presentation metadata keyed by parameter id (SSOT-07, DATA-03, UX-10).

Labels and captions are user-facing text and live in `ui/strings.py` (UX-20).
Unknown ids fall back to `GENERIC`, so a new server parameter still renders.
"""

from __future__ import annotations

from dataclasses import dataclass

from buzsak_app.domain.models import Parameter


@dataclass(frozen=True)
class ParameterPresentation:
    # Lower-case Material icon name; the UI maps it to a Flet icon with its own fallback.
    icon: str
    # Position within a device; lower first.
    order: int
    # Digits after the decimal point; None picks a default from the value type.
    decimals: int | None = None


GENERIC = ParameterPresentation(icon="sensors", order=1000)

_CATALOG: dict[str, ParameterPresentation] = {
    # PUMP (garden_plc)
    "pressure_bar": ParameterPresentation("speed", 10, decimals=2),
    "water_level_liters": ParameterPresentation("water", 20, decimals=0),
    "well_pump": ParameterPresentation("water_drop", 30),
    "tank_pump": ParameterPresentation("water_drop", 40),
    "left_sw": ParameterPresentation("toggle_on", 50),
    "right_sw": ParameterPresentation("toggle_on", 60),
    "switch_led": ParameterPresentation("lightbulb", 70),
    "wifi_led": ParameterPresentation("wifi", 80),
    # GREENHOUSE (valve_controller)
    "sensor_a_temperature_c": ParameterPresentation("thermostat", 10, decimals=1),
    "sensor_a_humidity_pct": ParameterPresentation("opacity", 20, decimals=1),
    "sensor_b_temperature_c": ParameterPresentation("thermostat", 30, decimals=1),
    "sensor_b_humidity_pct": ParameterPresentation("opacity", 40, decimals=1),
    "mode": ParameterPresentation("tune", 50),
    "relay1_mist": ParameterPresentation("shower", 60),
    "relay2_rain": ParameterPresentation("grain", 70),
    "relay3_drip": ParameterPresentation("water_drop", 80),
    "relay4_light": ParameterPresentation("light_mode", 90),
    "automation_target_pct": ParameterPresentation("track_changes", 100, decimals=0),
    "automation_duty": ParameterPresentation("percent", 110, decimals=0),
    "automation_period_s": ParameterPresentation("schedule", 120, decimals=0),
    "automation_elapsed_s": ParameterPresentation("timer", 130, decimals=0),
    "automation_valve_on": ParameterPresentation("shower", 140),
    "automation_sensor_valid": ParameterPresentation("check_circle", 150),
    "automation_time_synced": ParameterPresentation("sync", 160),
    # GARAGE (sonoff_minid)
    "on_off": ParameterPresentation("power_settings_new", 10),
}


def presentation_for(parameter_id: str) -> ParameterPresentation:
    return _CATALOG.get(parameter_id, GENERIC)


# KPIs the Overview card shows per device, when present (UX-03).
HEADLINE_PARAMETERS: tuple[str, ...] = (
    "pressure_bar",
    "water_level_liters",
    "sensor_a_temperature_c",
    "sensor_a_humidity_pct",
    "mode",
    "on_off",
)


def known_parameter_ids() -> frozenset[str]:
    return frozenset(_CATALOG)


@dataclass(frozen=True)
class NumericDisplay:
    text: str
    unit: str | None


def display_number(parameter: Parameter) -> NumericDisplay | None:
    """Format a numeric value with its unit; a ratio shows as a percentage (DATA-03).

    Returns None when there is no numeric value, so a missing value is never shown as 0.
    """
    value = parameter.value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    unit = parameter.unit
    decimals = presentation_for(parameter.id).decimals
    if unit == "ratio":
        value, unit = value * 100, "%"
        decimals = 0 if decimals is None else decimals
    if decimals is None:
        decimals = 0 if isinstance(value, int) else 1
    return NumericDisplay(text=f"{value:.{decimals}f}", unit=unit)
