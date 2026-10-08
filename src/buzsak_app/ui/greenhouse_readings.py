"""Dedicated Greenhouse automation, sensor and identity readouts (VLV-07/08, DATA-02)."""

from __future__ import annotations

import flet as ft

from buzsak_app.domain.models import Device, Parameter, ValueState
from buzsak_app.domain.presentation import display_number
from buzsak_app.ui import strings, theme
from buzsak_app.ui.components import StatusChip, muted_text, section_title
from buzsak_app.ui.theme import RADIUS, SPACING, TYPE
from buzsak_app.ui.view_models import Tone

_HANDLED_PARAMETER_IDS = frozenset({
    "firmware", "ip", "mode",
    "relay1_mist", "relay2_rain", "relay3_drip", "relay4_light",
    "relay1_controllable", "relay2_controllable", "relay3_controllable", "relay4_controllable",
    "relay1_always_manual", "relay2_always_manual", "relay3_always_manual", "relay4_always_manual",
    "automation_target_pct", "automation_duty", "automation_period_s", "automation_elapsed_s",
    "automation_valve_on", "automation_sensor_valid", "automation_time_synced",
    "rain_valve_on", "rain_start_hour", "rain_start_minute", "rain_duration_s",
    "rain_has_last_run", "rain_last_run_duration_s", "rain_time_synced",
    "sensor_a_temperature_c", "sensor_a_humidity_pct", "sensor_a_ok", "sensor_a_last_error", "sensor_a_age_s",
    "sensor_b_temperature_c", "sensor_b_humidity_pct", "sensor_b_ok", "sensor_b_last_error", "sensor_b_age_s",
})

_STATE_BADGES = {
    ValueState.STALE: (strings.STATE_STALE, "history", Tone.WARNING),
    ValueState.UNAVAILABLE: (strings.STATE_UNAVAILABLE, "cloud_off", Tone.ERROR),
    ValueState.INVALID: (strings.STATE_INVALID, "error_outline", Tone.ERROR),
    ValueState.NO_DATA: (strings.STATE_NO_DATA, "hourglass_empty", Tone.MUTED),
}


def _display_value(parameter: Parameter | None) -> str:
    if parameter is None:
        return strings.VALUE_MISSING
    if parameter.state is ValueState.NO_DATA:
        return strings.STATE_NO_DATA
    if parameter.value is None:
        return strings.VALUE_MISSING
    if isinstance(parameter.value, bool):
        return strings.VALUE_ON if parameter.value else strings.VALUE_OFF
    number = display_number(parameter)
    if number is not None:
        return f"{number.text} {number.unit}" if number.unit else number.text
    if parameter.id == "mode":
        return strings.mode_text(parameter.value)
    return str(parameter.value)


def _detail(parameter: Parameter | None) -> str:
    if parameter is None:
        return strings.VALUE_MISSING
    observed = (
        parameter.observed_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        if parameter.observed_at else strings.VALUE_MISSING
    )
    lines = [
        f"{parameter.id}: {_display_value(parameter)}", f"{strings.DETAIL_OBSERVED}: {observed}"]
    if parameter.issue:
        lines.append(f"{strings.DETAIL_PROBLEM}: {parameter.issue}")
    return "\n".join(lines)


class _Readout:
    def __init__(self, label: str) -> None:
        self._label = ft.Text(label, size=TYPE.caption,
                              color=ft.Colors.ON_SURFACE_VARIANT, expand=True)
        self._value = ft.Text(strings.VALUE_MISSING,
                              size=TYPE.body, weight=ft.FontWeight.W_600)
        self._badge = StatusChip()
        self._badge.control.visible = False
        self.control = ft.Row(
            [
                self._label,
                ft.Column(
                    [self._value, self._badge.control],
                    spacing=SPACING.xs,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    tight=True,
                ),
            ],
            spacing=SPACING.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    def update(
        self,
        parameter: Parameter | None,
        *,
        text: str | None = None,
        true_text: str | None = None,
        false_text: str | None = None,
    ) -> None:
        if text is not None:
            self._value.value = text
        elif parameter is not None and parameter.value is True and true_text:
            self._value.value = true_text
        elif parameter is not None and parameter.value is False and false_text:
            self._value.value = false_text
        else:
            self._value.value = _display_value(parameter)
        self.control.tooltip = text if parameter is None and text is not None else _detail(
            parameter)
        if parameter is None:
            self._badge.control.visible = text is None
            if text is None:
                self._badge.set(strings.STATE_UNAVAILABLE,
                                "cloud_off", Tone.ERROR)
            return
        badge = _STATE_BADGES.get(parameter.state)
        self._badge.control.visible = badge is not None
        if badge is not None:
            self._badge.set(*badge)


class _SensorPanel:
    def __init__(self, name: str, title: str) -> None:
        self._title = ft.Text(title, size=TYPE.title,
                              weight=ft.FontWeight.W_600)
        self._health = StatusChip()
        self._temperature = _Readout(strings.SENSOR_TEMPERATURE)
        self._humidity = _Readout(strings.SENSOR_HUMIDITY)
        self._age = muted_text()
        self._error = muted_text()
        self._error.visible = False
        self.control = ft.Container(
            content=ft.Column(
                [
                    ft.Row([self._title, self._health.control],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self._temperature.control,
                    self._humidity.control,
                    self._age,
                    self._error,
                ],
                spacing=SPACING.sm,
            ),
            padding=ft.Padding.all(SPACING.md),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=ft.BorderRadius.all(RADIUS.card),
            col={"xs": 12, "md": 12},
        )
        self._name = name

    def sync(self, device: Device) -> None:
        ok = device.parameter(f"{self._name}_ok")
        if ok is None or ok.state is not ValueState.GOOD or not isinstance(ok.value, bool):
            self._health.set(strings.STATE_UNAVAILABLE,
                             "cloud_off", Tone.ERROR)
        elif ok.value:
            self._health.set(strings.SENSOR_OK, "check_circle", Tone.OK)
        else:
            self._health.set(strings.SENSOR_FAULT, "error_outline", Tone.ERROR)
        self._temperature.update(
            device.parameter(f"{self._name}_temperature_c"))
        self._humidity.update(device.parameter(f"{self._name}_humidity_pct"))

        age = device.parameter(f"{self._name}_age_s")
        if age is None or age.state is not ValueState.GOOD or not isinstance(age.value, int):
            self._age.value = strings.SENSOR_AGE_MISSING
        elif age.value == 0:
            self._age.value = strings.SENSOR_NO_GOOD_FRAME
        else:
            self._age.value = strings.sensor_age(age.value)

        last_error = device.parameter(f"{self._name}_last_error")
        error = last_error.value if last_error and last_error.state is ValueState.GOOD else None
        self._error.value = strings.sensor_last_error(
            str(error)) if error else ""
        self._error.visible = bool(error)


class GreenhouseReadings:
    """Renders server-reported automation, sensor and identity values without optimistic state."""

    handled_parameter_ids = _HANDLED_PARAMETER_IDS

    def __init__(self, device: Device) -> None:
        self._device = device
        self._mode_badge = StatusChip(
            strings.STATE_FROZEN, "pause_circle_outline", Tone.MUTED)
        self._mode_badge.control.visible = False
        self._mist_target = _Readout(strings.MIST_TARGET)
        self._mist_duty = _Readout(strings.MIST_DUTY)
        self._mist_valve = _Readout(strings.MIST_VALVE)
        self._mist_sensor = _Readout(strings.AUTOMATION_SENSOR)
        self._mist_time = _Readout(strings.TIME_SYNC)
        self._mist_progress = ft.ProgressBar(
            value=None, bar_height=6, semantics_label=strings.MIST_PROGRESS)
        self._mist_progress_text = muted_text(strings.VALUE_MISSING)
        self._mist_panel = self._automation_panel(
            strings.MIST_AUTOMATION,
            [
                ft.Column([self._mist_target.control, self._mist_duty.control],
                          spacing=SPACING.sm),
                self._mist_progress,
                self._mist_progress_text,
                self._mist_valve.control,
                ft.Row([self._mist_sensor.control,
                       self._mist_time.control], spacing=SPACING.md),
            ],
        )

        self._rain_time = _Readout(strings.RAIN_START)
        self._rain_duration = _Readout(strings.RAIN_DURATION)
        self._rain_valve = _Readout(strings.RAIN_VALVE)
        self._rain_last_run = _Readout(strings.RAIN_LAST_RUN)
        self._rain_time_sync = _Readout(strings.TIME_SYNC)
        self._rain_missing = muted_text(strings.RAIN_NOT_REPORTED)
        self._rain_details = ft.Column(
            [
                self._rain_time.control,
                self._rain_duration.control,
                self._rain_valve.control,
                self._rain_last_run.control,
                self._rain_time_sync.control,
            ],
            spacing=SPACING.sm,
        )
        self._rain_panel = self._automation_panel(
            strings.RAIN_AUTOMATION,
            [self._rain_details, self._rain_missing],
        )
        self._sensors = (
            _SensorPanel("sensor_a", strings.SENSOR_A),
            _SensorPanel("sensor_b", strings.SENSOR_B),
        )
        self._firmware = _Readout(strings.DEVICE_FIRMWARE)
        self._ip = _Readout(strings.DEVICE_IP)
        self.control = ft.Column(
            [
                ft.Row([section_title(strings.AUTOMATION), self._mode_badge.control],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.ResponsiveRow(
                    [self._mist_panel, self._rain_panel],
                    spacing=SPACING.sm,
                    run_spacing=SPACING.sm,
                ),
                section_title(strings.SENSORS),
                ft.ResponsiveRow(
                    [sensor.control for sensor in self._sensors],
                    spacing=SPACING.sm,
                    run_spacing=SPACING.sm,
                ),
                ft.Row(
                    [self._firmware.control, self._ip.control],
                    spacing=SPACING.lg,
                    wrap=True,
                ),
            ],
            spacing=SPACING.md,
        )
        self.sync(device)

    @staticmethod
    def _automation_panel(title: str, contents: list[ft.Control]) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [ft.Text(title, size=TYPE.body,
                         weight=ft.FontWeight.W_600), *contents],
                spacing=SPACING.sm,
            ),
            padding=ft.Padding.all(SPACING.md),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=ft.BorderRadius.all(RADIUS.card),
            col={"xs": 12, "md": 12},
        )

    def sync(self, device: Device) -> None:
        self._device = device
        mode = device.parameter("mode")
        frozen = mode is not None and mode.is_current and mode.value == "manual"
        self._mode_badge.control.visible = frozen
        self._mist_panel.opacity = theme.DIMMED_OPACITY if frozen else 1.0
        self._rain_panel.opacity = theme.DIMMED_OPACITY if frozen else 1.0

        self._mist_target.update(device.parameter("automation_target_pct"))
        self._mist_duty.update(device.parameter("automation_duty"))
        self._mist_valve.update(device.parameter("automation_valve_on"))
        self._mist_sensor.update(
            device.parameter("automation_sensor_valid"),
            true_text=strings.SENSOR_VALID, false_text=strings.SENSOR_INVALID,
        )
        self._mist_time.update(
            device.parameter("automation_time_synced"),
            true_text=strings.TIME_SYNCHRONIZED,
            false_text=strings.TIME_UNSYNCHRONIZED,
        )
        elapsed = device.parameter("automation_elapsed_s")
        period = device.parameter("automation_period_s")
        if (
            elapsed is not None and period is not None
            and elapsed.is_current and period.is_current
            and isinstance(elapsed.value, (int, float))
            and isinstance(period.value, (int, float)) and period.value > 0
        ):
            fraction = min(1.0, max(0.0, elapsed.value / period.value))
            self._mist_progress.value = fraction
            self._mist_progress.visible = True
            self._mist_progress_text.value = strings.mist_progress(
                int(elapsed.value), int(period.value), round(fraction * 100))
        else:
            self._mist_progress.visible = False
            self._mist_progress_text.value = strings.VALUE_MISSING

        rain_parameters = (
            "rain_valve_on", "rain_start_hour", "rain_start_minute",
            "rain_duration_s", "rain_has_last_run", "rain_time_synced",
        )
        rain_reported = any(device.parameter(parameter_id)
                            is not None for parameter_id in rain_parameters)
        self._rain_missing.visible = not rain_reported
        self._rain_details.visible = rain_reported
        if rain_reported:
            self._rain_time.update(self._rain_start(device))
            self._rain_duration.update(device.parameter("rain_duration_s"))
            self._rain_valve.update(device.parameter("rain_valve_on"))
            self._rain_time_sync.update(
                device.parameter("rain_time_synced"),
                true_text=strings.TIME_SYNCHRONIZED,
                false_text=strings.TIME_UNSYNCHRONIZED,
            )
            has_run = device.parameter("rain_has_last_run")
            if has_run is not None and has_run.is_current and has_run.value is False:
                self._rain_last_run.update(
                    None, text=strings.RAIN_NO_PREVIOUS_RUN)
            else:
                self._rain_last_run.update(
                    device.parameter("rain_last_run_duration_s"))

        for sensor in self._sensors:
            sensor.sync(device)
        self._firmware.update(device.parameter("firmware"))
        self._ip.update(device.parameter("ip"))

    @staticmethod
    def _rain_start(device: Device) -> Parameter | None:
        hour = device.parameter("rain_start_hour")
        minute = device.parameter("rain_start_minute")
        if hour is None or minute is None:
            return None
        if hour.observed_at is None or minute.observed_at is None:
            return Parameter(
                id="rain_start_time", category="configuration", unit=None,
                value=None, value_type=None, state=ValueState.INVALID,
                observed_at=None, last_changed_at=None,
                revision=max(hour.revision, minute.revision),
                issue="rain start timestamp is missing",
            )
        if (
            hour.is_current and minute.is_current
            and type(hour.value) is int and type(minute.value) is int
            and 0 <= hour.value <= 23 and 0 <= minute.value <= 59
        ):
            composite_state = ValueState.GOOD
            display_value: str | None = f"{hour.value:02d}:{minute.value:02d}"
        else:
            states = {hour.state, minute.state}
            composite_state = next(
                (state for state in (ValueState.INVALID, ValueState.UNAVAILABLE,
                                     ValueState.NO_DATA, ValueState.STALE) if state in states),
                ValueState.INVALID,
            )
            display_value = None
        observed_values = [value for value in (
            hour.observed_at, minute.observed_at) if value]
        observed = min(observed_values) if observed_values else None
        changed_values = [value for value in (
            hour.last_changed_at, minute.last_changed_at) if value]
        return Parameter(
            id="rain_start_time", category="configuration", unit=None,
            value=display_value, value_type="string" if display_value is not None else None,
            state=composite_state,
            observed_at=observed,
            last_changed_at=max(changed_values) if changed_values else None,
            revision=max(hour.revision, minute.revision),
            issue="start hour or minute is invalid" if composite_state is ValueState.INVALID else None,
        )
