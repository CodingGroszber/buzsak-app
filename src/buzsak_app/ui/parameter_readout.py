"""Shared compact telemetry readouts with explicit quality states (DATA-02, UX-25)."""

from __future__ import annotations

import math

import flet as ft

from buzsak_app.domain.models import Parameter, ValueState
from buzsak_app.domain.presentation import display_number
from buzsak_app.ui import strings, theme
from buzsak_app.ui.components import StatusChip
from buzsak_app.ui.theme import SPACING, TYPE
from buzsak_app.ui.view_models import Tone

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
    if parameter.id in {"mode", "switch_mode"}:
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


class ParameterReadout:
    """Render a parameter without conflating absent, false and stale (DATA-02)."""

    def __init__(self, label: str) -> None:
        self._label = ft.Text(label, size=TYPE.caption,
                              color=ft.Colors.ON_SURFACE_VARIANT, expand=True)
        self._value = ft.Text(strings.VALUE_MISSING,
                              size=TYPE.body, weight=ft.FontWeight.W_600)
        self._badge = StatusChip()
        self._badge.control.visible = False
        self.control = ft.Row(
            [self._label, ft.Column(
                [self._value, self._badge.control], spacing=SPACING.xs,
                horizontal_alignment=ft.CrossAxisAlignment.END, tight=True,
            )],
            spacing=SPACING.sm,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    def update(
        self, parameter: Parameter | None, *, text: str | None = None,
        true_text: str | None = None, false_text: str | None = None,
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


class SensorReadout(ParameterReadout):
    """Compact status/name/value row gated by sensor signal quality (DATA-02, UX-29)."""

    def __init__(self, label: str) -> None:
        super().__init__(label)
        self._parameter: Parameter | None = None
        self._signal: Parameter | None = None
        self._indicator = ft.Icon(ft.Icons.CLOUD_OFF, size=TYPE.body)
        self._label.size = TYPE.body
        self._label.weight = ft.FontWeight.W_600
        self._label.color = None
        self.control.controls.insert(0, self._indicator)

    def update(
        self, parameter: Parameter | None, *, text: str | None = None,
        true_text: str | None = None, false_text: str | None = None,
    ) -> None:
        super().update(parameter, text=text, true_text=true_text, false_text=false_text)
        self._parameter = parameter
        self._refresh_indicator()

    def set_signal(self, signal: Parameter | None) -> None:
        """Apply the independent server validity flag, never infer a healthy probe (DATA-02)."""
        self._signal = signal
        self._refresh_indicator()

    def _refresh_indicator(self) -> None:
        states = [parameter.state if parameter is not None else ValueState.UNAVAILABLE
                  for parameter in (self._parameter, self._signal)]
        quality = next((state for state in (
            ValueState.INVALID, ValueState.UNAVAILABLE, ValueState.NO_DATA, ValueState.STALE
        ) if state in states), ValueState.GOOD)
        if quality is ValueState.GOOD and (
            type(self._parameter.value) not in (int, float)
            or not math.isfinite(self._parameter.value)
            or type(self._signal.value) is not bool
        ):
            quality = ValueState.INVALID
        if quality is not ValueState.GOOD:
            status, _, tone = _STATE_BADGES[quality]
            icon = {
                ValueState.INVALID: ft.Icons.ERROR_OUTLINE,
                ValueState.UNAVAILABLE: ft.Icons.CLOUD_OFF,
                ValueState.NO_DATA: ft.Icons.HOURGLASS_EMPTY,
                ValueState.STALE: ft.Icons.HISTORY,
            }[quality]
        elif self._signal.value is False:
            status, icon, tone = strings.SENSOR_FAULT, ft.Icons.ERROR_OUTLINE, Tone.ERROR
        else:
            status, icon, tone = strings.SENSOR_OK, ft.Icons.CHECK_CIRCLE, Tone.OK
        self._indicator.icon = icon
        self._indicator.color = theme.tone_color(tone)
        self._indicator.tooltip = self._indicator.semantics_label = status
        self._badge.control.visible = quality is not ValueState.GOOD or self._signal.value is False
        if self._badge.control.visible:
            self._badge.set(
                status, "history" if quality is ValueState.STALE else "error_outline", tone)
        self.control.tooltip = "\n".join(
            (_detail(self._parameter), _detail(self._signal)))
