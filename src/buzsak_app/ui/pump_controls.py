"""Compact PLC telemetry and a one-shot server refill intent (CTL-12, UX-25)."""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping

import flet as ft

from buzsak_app.api.client import ApiError, AmbiguousCommandResult, CommandApiError
from buzsak_app.domain.models import Device, HealthStatus, ValueState
from buzsak_app.ui import strings, theme
from buzsak_app.ui.command_visuals import command_state_tone
from buzsak_app.ui.components import muted_text, section_title
from buzsak_app.ui.greenhouse_controls import CommandHandler, CommandLookup
from buzsak_app.ui.parameter_readout import ParameterReadout, SensorReadout
from buzsak_app.ui.theme import SPACING
from buzsak_app.ui.view_models import Tone, device_identity

_TERMINAL = frozenset({"confirmed", "failed", "expired", "cancelled"})
_SENSOR_SIGNALS = {"water_level_liters": "water_level_signal",
                   "pressure_bar": "pressure_signal"}


class PumpControls:
    """Gate refill using fresh server state; never write pump outputs (CTL-12)."""

    def __init__(
        self, device: Device, *, page: ft.Page | None,
        on_command: CommandHandler | None, on_check_command: CommandLookup | None = None,
    ) -> None:
        self._device = device
        self._page = page
        self._on_command = on_command
        self._on_check_command = on_check_command
        self._busy = False
        self._locked = False
        self._available = True
        self._command_id: str | None = None
        self._readouts: dict[str, ParameterReadout] = {}
        self._reason = muted_text()
        self._message = muted_text()
        self._fill = ft.FilledButton(
            strings.PUMP_FILL_TANK, icon=ft.Icons.WATER_DROP, on_click=self._request_fill,
        )
        self._check_status = ft.TextButton(
            strings.COMMAND_CHECK_STATUS, visible=False, on_click=self._check_command_status,
        )
        groups = []
        for title, identifiers in strings.PUMP_READOUT_GROUPS:
            rows = []
            for identifier in identifiers:
                readout_type = SensorReadout if identifier in _SENSOR_SIGNALS else ParameterReadout
                readout = readout_type(
                    strings.PUMP_PARAMETER_LABELS[identifier])
                self._readouts[identifier] = readout
                if rows and not isinstance(readout, SensorReadout):
                    rows.append(ft.Divider(height=1, thickness=1))
                rows.append(readout.control)
            groups.append(
                ft.Column([section_title(title), *rows],
                          spacing=SPACING.xs if all(identifier in _SENSOR_SIGNALS for identifier in identifiers) else SPACING.sm))
        self.handled_parameter_ids = frozenset(strings.PUMP_PARAMETER_LABELS)
        self.control = ft.Column([
            ft.Column([
                section_title(strings.PUMP_CONTROL), self._fill, self._reason,
                muted_text(
                    strings.PUMP_REFILL_WARNING), self._message, self._check_status,
            ], spacing=SPACING.sm),
            *groups,
        ], spacing=SPACING.lg)
        self.sync(device)

    def header_info(self) -> str:
        """Keep PLC identity discreet and quality-aware in the header (UX-25)."""
        return device_identity(self._device)

    def _current(self, identifier: str):
        parameter = self._device.parameter(identifier)
        return parameter.value if parameter is not None and parameter.state is ValueState.GOOD else None

    def _disabled_reason(self) -> str:
        capability = self._device.capability("refill")
        if capability is None:
            return strings.PUMP_REFILL_UNAVAILABLE
        if not capability.enabled:
            return capability.disabled_reason or strings.PUMP_REFILL_UNAVAILABLE
        if not isinstance(capability.params_schema, Mapping) or capability.params_schema:
            return strings.CONTROL_SCHEMA_INVALID
        if self._locked:
            return strings.PUMP_REFILL_UNCERTAIN
        if self._on_command is None:
            return strings.CONTROL_NO_HANDLER
        if not self._available or not self._device.enabled or self._device.health.status is not HealthStatus.HEALTHY:
            return strings.CONTROL_DEVICE_UNAVAILABLE
        code = self._current("switch_mode_code")
        if type(code) is not int or code != 1 or self._current("switch_mode") != "automatic":
            return strings.PUMP_REFILL_REQUIRES_AUTO
        if self._current("refill_button") is not False or self._current("refill_active") is not False:
            return strings.PUMP_REFILL_NOT_IDLE
        level = self._current("water_level_liters")
        if (
            self._current("water_level_signal") is not True
            or type(level) not in (int, float) or not math.isfinite(level) or level < 0
        ):
            return strings.PUMP_REFILL_LEVEL_UNAVAILABLE
        if level >= 1000:
            return strings.PUMP_REFILL_TANK_FULL
        return ""

    def sync(self, device: Device, *, changed: frozenset[str] | None = None) -> None:
        """Update server-reported telemetry in place without optimistic state (CTL-05)."""
        self._device = device
        for identifier, readout in self._readouts.items():
            signal_id = _SENSOR_SIGNALS.get(identifier)
            if changed is None or identifier in changed or signal_id in changed:
                readout.update(device.parameter(identifier))
                if isinstance(readout, SensorReadout):
                    readout.set_signal(device.parameter(signal_id))
        reason = self._disabled_reason()
        self._reason.value = reason
        self._reason.visible = bool(reason)
        self._fill.disabled = self._busy or bool(reason)

    def set_available(self, available: bool) -> None:
        """Fail closed for offline, overdue or globally stale snapshots (CTL-12)."""
        self._available = available
        self.sync(self._device, changed=frozenset())

    def _update(self) -> None:
        self.sync(self._device, changed=frozenset())
        if self._page is not None:
            self._page.update()

    def _set_status(
        self, status: str, reason: str | None = None, command_id: str | None = None,
    ) -> None:
        if command_id:
            self._command_id = command_id
        self._message.value = strings.command_status(status, reason)
        self._message.color = theme.tone_color(command_state_tone(status))
        if status == "uncertain":
            self._locked = True
        self._check_status.visible = bool(
            self._command_id and self._on_check_command and status not in _TERMINAL
        )
        self._update()

    async def _request_fill(self, _event: ft.Event) -> None:
        if self._busy or self._disabled_reason() or self._on_command is None:
            return
        self._busy = True
        self._message.value = strings.COMMAND_SUBMITTING
        self._message.color = theme.tone_color(Tone.WARNING)
        self._update()
        try:
            status = await self._on_command(
                self._device.id, "refill", {}, str(
                    uuid.uuid4()), self._set_status,
            )
            self._set_status(status)
        except CommandApiError as error:
            self._message.value = f"{strings.COMMAND_REJECTED}: {error}"
            self._message.color = theme.tone_color(Tone.ERROR)
        except (AmbiguousCommandResult, ApiError):
            self._set_status("uncertain")
        except Exception:
            self._set_status("uncertain")
        finally:
            self._busy = False
            self._update()

    async def _check_command_status(self, _event: ft.Event) -> None:
        if self._busy or self._command_id is None or self._on_check_command is None:
            return
        self._busy = True
        self._update()
        try:
            status = await self._on_check_command(self._command_id, self._set_status)
            if status in _TERMINAL:
                self._locked = False
            self._set_status(status)
        except Exception:
            self._set_status("uncertain")
        finally:
            self._busy = False
            self._update()
