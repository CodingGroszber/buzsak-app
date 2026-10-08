"""Greenhouse mode and relay controls, gated by fresh server state (VLV-02/03, CTL-02, SSOT-08)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import flet as ft

from buzsak_app.api.client import ApiError, AmbiguousCommandResult, CommandApiError
from buzsak_app.domain.models import Device, HealthStatus, Parameter, ValueState
from buzsak_app.ui import strings, theme
from buzsak_app.ui.components import muted_text, section_title
from buzsak_app.ui.greenhouse_readings import GreenhouseReadings
from buzsak_app.ui.theme import SPACING, TYPE
from buzsak_app.ui.view_models import Tone

logger = logging.getLogger(__name__)

CommandHandler = Callable[
    [str, str, Mapping[str, Any], str, Callable[[str, str | None, str | None], None]],
    Awaitable[str],
]
CommandLookup = Callable[
    [str, Callable[[str, str | None, str | None], None]], Awaitable[str]
]

_OUTPUTS = (
    ("relay1", "relay1_mist", "Mist"),
    ("relay2", "relay2_rain", "Rain"),
    ("relay3", "relay3_drip", "Drip"),
    ("relay4", "relay4_light", "Light"),
)
_TERMINAL = frozenset(
    {"confirmed", "failed", "expired", "cancelled", "uncertain"})
_COMMAND_TONES = {
    "pending": Tone.MUTED,
    "dispatching": Tone.WARNING,
    "sent": Tone.WARNING,
    "acknowledged": Tone.WARNING,
    "confirmed": Tone.OK,
    "failed": Tone.ERROR,
    "expired": Tone.ERROR,
    "cancelled": Tone.MUTED,
    "uncertain": Tone.WARNING,
}


def _current(device: Device, parameter_id: str) -> Parameter | None:
    parameter = device.parameter(parameter_id)
    return parameter if parameter is not None and parameter.state is ValueState.GOOD else None


def _bool(device: Device, parameter_id: str) -> bool | None:
    parameter = _current(device, parameter_id)
    return parameter.value if parameter is not None and isinstance(parameter.value, bool) else None


def _mode(device: Device) -> str | None:
    parameter = _current(device, "mode")
    if parameter is not None and parameter.value in {"manual", "automatic"}:
        return str(parameter.value)
    return None


def _schema_accepts(device: Device, action_id: str, params: Mapping[str, Any]) -> bool:
    capability = device.capability(action_id)
    schema = capability.params_schema if capability is not None else None
    if not isinstance(schema, Mapping) or set(schema) != set(params):
        return False
    for key, expected in schema.items():
        value = params[key]
        if expected == "bool":
            if type(value) is not bool:
                return False
        elif isinstance(expected, list):
            if value not in expected:
                return False
        else:
            return False
    return True


class GreenhouseControls:
    def __init__(
        self,
        device: Device,
        *,
        page: ft.Page | None,
        on_command: CommandHandler | None,
        on_check_command: CommandLookup | None = None,
    ) -> None:
        self.device_id = device.id
        self._page = page
        self._on_command = on_command
        self._on_check_command = on_check_command
        self._device = device
        self._busy = False
        self._locked = False
        self._intent_keys: dict[str, str] = {}
        self._active_intent: str | None = None
        self._command_id: str | None = None
        self._last_action: str | None = None
        self._last_params: Mapping[str, Any] | None = None
        self._mode_hint = muted_text()
        self._reason = muted_text()
        self._message = muted_text()
        self._check_status = ft.TextButton(
            strings.COMMAND_CHECK_STATUS,
            visible=False,
            on_click=self._check_command_status,
        )
        self._retry = ft.TextButton(
            strings.COMMAND_RETRY,
            visible=False,
            on_click=self._retry_command,
        )
        self._mode = ft.SegmentedButton(
            segments=[
                ft.Segment(value="manual", label=strings.MODE_MANUAL),
                ft.Segment(value="automatic", label=strings.MODE_AUTOMATIC),
            ],
            selected=[],
            allow_empty_selection=True,
            show_selected_icon=False,
            on_change=self._mode_changed,
        )
        self._relay_rows: dict[str, tuple[ft.Text, ft.FilledButton]] = {}
        self._relay_dots: dict[str, ft.Icon] = {}
        self._relay_hints: dict[str, ft.Text] = {}
        rows: list[ft.Control] = []
        for output_id, _, label in _OUTPUTS:
            state = ft.Text(strings.VALUE_MISSING,
                            size=TYPE.body, weight=ft.FontWeight.W_600)
            dot = ft.Icon(ft.Icons.CIRCLE, size=12, color=ft.Colors.OUTLINE)
            hint = ft.Text("", size=TYPE.caption,
                           color=ft.Colors.ON_SURFACE_VARIANT)

            async def on_relay_click(
                event: ft.Event, relay_name: str = output_id
            ) -> None:
                await self._relay_clicked(relay_name)

            button = ft.FilledButton(
                strings.VALUE_MISSING,
                icon=ft.Icons.TOGGLE_OFF,
                on_click=on_relay_click,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=4),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                ),
            )
            button.width = 96
            button.height = 40
            row = ft.Row(
                [
                    dot,
                    ft.Text(label, expand=True, size=TYPE.body),
                    hint,
                    state,
                    button,
                ],
                spacing=SPACING.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            rows.append(row)
            self._relay_rows[output_id] = (state, button)
            self._relay_dots[output_id] = dot
            self._relay_hints[output_id] = hint
        self._rain_note = muted_text()
        self._readings = GreenhouseReadings(device)
        valve_rows: list[ft.Control] = [section_title(strings.VALVES)]
        for index, row in enumerate(rows):
            if index:
                valve_rows.append(ft.Divider(height=1, thickness=1))
            valve_rows.append(row)
        self._control_panel = ft.Column(
            [
                section_title(strings.GREENHOUSE_CONTROL),
                ft.Row([self._mode], expand=True),
                self._mode_hint,
                self._reason,
                *valve_rows,
                self._message,
                self._check_status,
                self._retry,
            ],
            spacing=SPACING.sm,
        )
        self.control = ft.Column(
            [self._control_panel, self._readings.control],
            spacing=SPACING.lg,
        )
        self.sync(device)

    def sync(self, device: Device) -> None:
        self._device = device
        self._readings.sync(device)
        mode = _mode(device)
        self._mode.selected = [mode] if mode else []
        mode_capability = device.capability("set_mode")
        mode_ready = (
            self._on_command is not None
            and self._not_locked()
            and mode_capability is not None
            and mode_capability.enabled
            and _schema_accepts(device, "set_mode", {"value": mode or ""})
            and mode is not None
            and device.health.status is HealthStatus.HEALTHY
        )
        self._mode.disabled = not mode_ready or self._busy
        self._mode_hint.value = (
            strings.MODE_MANUAL_HINT if mode == "manual"
            else strings.MODE_AUTOMATIC_HINT if mode == "automatic"
            else strings.MODE_UNKNOWN_HINT
        )
        output_capability = device.capability("set_output")
        disabled_capability = (
            mode_capability if mode_capability is not None and not mode_capability.enabled
            else output_capability if output_capability is not None and not output_capability.enabled
            else mode_capability
        )
        self._reason.value = self._disabled_reason(
            disabled_capability, mode_ready)
        self._reason.visible = bool(self._reason.value)

        for output_id, parameter_id, label in _OUTPUTS:
            state_text, button = self._relay_rows[output_id]
            state = _bool(device, parameter_id)
            controllable = _bool(device, f"{output_id}_controllable")
            always_manual = _bool(device, f"{output_id}_always_manual")
            state_text.value = (
                strings.VALUE_OPEN if state is True else
                strings.VALUE_CLOSED if state is False else strings.VALUE_MISSING
            )
            button.content = state_text.value
            button.icon = ft.Icons.TOGGLE_ON if state is True else ft.Icons.TOGGLE_OFF
            self._relay_dots[output_id].color = (
                ft.Colors.PRIMARY if state is True else ft.Colors.OUTLINE)
            button.style = ft.ButtonStyle(
                bgcolor=(ft.Colors.PRIMARY_CONTAINER if state is True
                         else ft.Colors.ERROR_CONTAINER),
                color=(ft.Colors.ON_PRIMARY_CONTAINER if state is True
                       else ft.Colors.ON_ERROR_CONTAINER),
                shape=ft.RoundedRectangleBorder(radius=4),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            )
            button.tooltip = strings.relay_tooltip(label, state)
            capability = device.capability("set_output")
            allowed_mode = mode == "manual" or (
                mode == "automatic" and always_manual is True)
            enabled = (
                self._on_command is not None
                and self._not_locked()
                and capability is not None
                and capability.enabled
                and _schema_accepts(
                    device, "set_output", {"name": output_id, "state": state})
                and device.health.status is HealthStatus.HEALTHY
                and state is not None
                and controllable is True
                and always_manual is not None
                and mode is not None
                and allowed_mode
            )
            button.disabled = not enabled or self._busy
            self._relay_hints[output_id].value = self._relay_hint(
                output_id, device)

    @staticmethod
    def _relay_hint(output_id: str, device: Device) -> str:
        if output_id == "relay1":
            duty = _current(device, "automation_duty")
            period = _current(device, "automation_period_s")
            if (
                duty is None or period is None
                or not isinstance(duty.value, (int, float))
                or not isinstance(period.value, (int, float))
            ):
                return ""
            return strings.mist_run_hint(duty.value * period.value / 60)
        if output_id == "relay2":
            hour = _current(device, "rain_start_hour")
            minute = _current(device, "rain_start_minute")
            duration = _current(device, "rain_duration_s")
            if (
                hour is None or minute is None or duration is None
                or type(hour.value) is not int or type(minute.value) is not int
                or type(duration.value) is not int
            ):
                return ""
            return strings.rain_run_hint(
                f"{hour.value:02d}:{minute.value:02d}", round(duration.value / 60))
        return ""

    def _not_locked(self) -> bool:
        return not self._locked

    def _disabled_reason(self, capability, ready: bool) -> str:
        if capability is not None and not capability.enabled and capability.disabled_reason:
            return capability.disabled_reason
        if self._locked:
            return strings.COMMAND_UNCERTAIN_LOCK
        if self._device.health.status is not HealthStatus.HEALTHY:
            return strings.CONTROL_DEVICE_UNAVAILABLE
        if _mode(self._device) is None:
            return strings.CONTROL_MODE_UNAVAILABLE
        if not ready and self._on_command is None:
            return strings.CONTROL_NO_HANDLER
        return ""

    def _show_command_status(self, status: str, reason: str | None = None) -> None:
        self._message.value = strings.command_status(status, reason)
        self._message.color = theme.tone_color(
            _COMMAND_TONES.get(status, Tone.NEUTRAL))

    async def _relay_clicked(self, output_id: str) -> None:
        suffix = next(parameter_id for relay, parameter_id,
                      _ in _OUTPUTS if relay == output_id)
        state = _bool(self._device, suffix)
        if state is None:
            return
        await self._run("set_output", {"name": output_id, "state": not state})

    async def _mode_changed(self, event: ft.Event) -> None:
        selection = event.control.selected
        requested = selection[0] if selection else None
        current = _mode(self._device)
        self._mode.selected = [current] if current else []
        if requested not in {"manual", "automatic"} or requested == current:
            if self._page is not None:
                self._page.update()
            return
        capability = self._device.capability("set_mode")
        if capability is None or not capability.enabled or self._mode.disabled:
            if self._page is not None:
                self._page.update()
            return
        await self._run("set_mode", {"value": requested})

    async def _run(self, action_id: str, params: Mapping[str, Any]) -> None:
        if self._on_command is None or self._busy or self._locked:
            return
        if not self._can_submit(action_id, params):
            self._message.value = (
                strings.CONTROL_SCHEMA_INVALID
                if not _schema_accepts(self._device, action_id, params)
                else self._disabled_reason(
                    self._device.capability(action_id), ready=False)
            )
            self._message.color = theme.tone_color(Tone.ERROR)
            if self._page is not None:
                self._page.update()
            return
        intent = json.dumps([action_id, params],
                            sort_keys=True, separators=(",", ":"))
        key = self._intent_keys.setdefault(intent, str(uuid.uuid4()))
        self._active_intent = intent
        self._last_action = action_id
        self._last_params = dict(params)
        self._retry.visible = False
        self._busy = True
        self._message.value = strings.COMMAND_SUBMITTING
        self._message.color = theme.tone_color(Tone.WARNING)
        self.sync(self._device)
        if self._page is not None:
            self._page.update()
        try:
            status = await self._on_command(
                self.device_id, action_id, params, key, self._set_status)
            if status in _TERMINAL:
                if status == "confirmed":
                    self._intent_keys.pop(intent, None)
                    self._active_intent = None
            if status == "uncertain":
                self._locked = True
                self._show_command_status("uncertain")
                self._message.value += f" · {strings.COMMAND_UNCERTAIN_LOCK}"
        except AmbiguousCommandResult as error:
            self._show_command_status("uncertain")
            self._message.value += f". {strings.COMMAND_RETRY_SAME_INTENT}"
            self._retry.visible = True
        except CommandApiError as error:
            self._intent_keys.pop(intent, None)
            self._active_intent = None
            self._message.value = f"{strings.COMMAND_REJECTED}: {error}"
            self._message.color = theme.tone_color(Tone.ERROR)
        except ApiError as error:
            self._show_command_status("uncertain")
            self._message.value += f" · {error}"
            self._check_status.visible = bool(
                self._command_id and self._on_check_command)
        except Exception as error:
            logger.warning("command flow failed: %s", type(error).__name__)
            self._message.value = strings.COMMAND_STATUS_UNAVAILABLE
            self._message.color = theme.tone_color(Tone.WARNING)
        finally:
            self._busy = False
            self.sync(self._device)
            if self._page is not None:
                self._page.update()

    def _set_status(
        self, status: str, reason: str | None = None, command_id: str | None = None
    ) -> None:
        if command_id:
            self._command_id = command_id
        self._show_command_status(status, reason)
        if status == "uncertain":
            self._locked = True
            self._check_status.visible = bool(
                self._command_id and self._on_check_command)
            self._message.value += f" · {strings.COMMAND_UNCERTAIN_LOCK}"
        elif status in {"confirmed", "failed", "expired", "cancelled"}:
            self._check_status.visible = False
            self._retry.visible = False
        if self._page is not None:
            self._page.update()

    async def _check_command_status(self, _: ft.Event) -> None:
        if self._command_id is None or self._on_check_command is None:
            return
        try:
            status = await self._on_check_command(self._command_id, self._set_status)
        except ApiError:
            self._message.value = strings.COMMAND_STATUS_UNAVAILABLE
            self._message.color = theme.tone_color(Tone.WARNING)
            status = "uncertain"
        except Exception as error:
            logger.warning("command status check failed: %s",
                           type(error).__name__)
            self._message.value = strings.COMMAND_STATUS_UNAVAILABLE
            self._message.color = theme.tone_color(Tone.WARNING)
            status = "uncertain"
        if status in {"confirmed", "failed", "expired", "cancelled"}:
            if status == "confirmed" and self._active_intent is not None:
                self._intent_keys.pop(self._active_intent, None)
            if status == "confirmed":
                self._active_intent = None
            self._command_id = None
            self._locked = False
            self._check_status.visible = False
            self._show_command_status(status)
        elif status != "uncertain":
            self._show_command_status(status)
            self._check_status.visible = True
        self.sync(self._device)
        if self._page is not None:
            self._page.update()

    def _can_submit(self, action_id: str, params: Mapping[str, Any]) -> bool:
        device = self._device
        capability = device.capability(action_id)
        if (
            capability is None
            or not capability.enabled
            or device.health.status is not HealthStatus.HEALTHY
            or not _schema_accepts(device, action_id, params)
            or _mode(device) is None
        ):
            return False
        if action_id == "set_mode":
            return True
        if action_id != "set_output":
            return False
        name = params.get("name")
        if not isinstance(name, str):
            return False
        state_parameter = next(
            (parameter_id for relay, parameter_id, _ in _OUTPUTS if relay == name), None)
        return (
            state_parameter is not None
            and _bool(device, state_parameter) is not None
            and _bool(device, f"{name}_controllable") is True
            and _bool(device, f"{name}_always_manual") is not None
            and (_mode(device) == "manual" or (
                _mode(device) == "automatic"
                and _bool(device, f"{name}_always_manual") is True
            ))
        )

    async def _retry_command(self, _: ft.Event) -> None:
        if self._last_action is None or self._last_params is None:
            return
        await self._run(self._last_action, self._last_params)
