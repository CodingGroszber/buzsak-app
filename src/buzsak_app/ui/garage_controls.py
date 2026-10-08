"""Garage pulse controls using server-reported state (CTL-02, CTL-03, CTL-11)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import flet as ft

from buzsak_app.api.client import ApiError, AmbiguousPulseResult, PulseRejected
from buzsak_app.domain.models import Device
from buzsak_app.ui import strings, theme
from buzsak_app.ui.command_visuals import (
    StateVisual,
    garage_relay_visual,
    pulse_button_visual,
)
from buzsak_app.ui.components import StatusChip, icon_for, muted_text
from buzsak_app.ui.control_styles import state_button_style
from buzsak_app.ui.theme import SPACING, TYPE
from buzsak_app.ui.view_models import Tone

logger = logging.getLogger(__name__)

PulseStatusCallback = Callable[[str, str | None, str | None], None]
PulseHandler = Callable[[str, datetime | None,
                         PulseStatusCallback], Awaitable[str]]
PulseLookup = Callable[[str, datetime | None,
                        PulseStatusCallback], Awaitable[str]]


class GaragePulseControl:
    def __init__(
        self,
        device: Device,
        *,
        page: ft.Page | None,
        on_pulse: PulseHandler | None,
        on_check: PulseLookup | None,
    ) -> None:
        self.device_id = device.id
        self._page = page
        self._device = device
        self._on_pulse = on_pulse
        self._on_check = on_check
        self._busy = False
        self._baseline = device.last_pulse.requested_at if device.last_pulse else None
        initial_status = device.last_pulse.status if device.last_pulse else None
        self._uncertain = initial_status == "uncertain"
        self._operation_status = (
            initial_status
            if initial_status in {"pending", "dispatching", "sent", "uncertain"}
            else None
        )
        self._message = ft.Text(
            strings.pulse_status(initial_status, device.last_pulse.error)
            if self._operation_status and device.last_pulse else "",
            size=TYPE.caption,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
            visible=self._operation_status is not None,
        )
        self._check = ft.TextButton(
            strings.COMMAND_CHECK_STATUS,
            visible=self._operation_status is not None,
            on_click=self._check_status,
        )
        self._relay = StatusChip()
        self._relay.control.tooltip = strings.GARAGE_POSITION_NOTE
        self._label = ft.Text(
            strings.garage_label(device.id),
            size=TYPE.title,
            weight=ft.FontWeight.W_600,
        )
        self._button = ft.FilledButton(
            content=strings.GARAGE_TRIGGER,
            icon=ft.Icons.POWER_SETTINGS_NEW,
            on_click=self._pulse,
            style=state_button_style(Tone.OK),
            height=44,
            width=112,
            tooltip=strings.GARAGE_TRIGGER_TOOLTIP,
        )
        self._reason = muted_text()
        self._content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [self._label, self._relay.control, self._reason],
                            spacing=SPACING.xs,
                            expand=True,
                        ),
                        self._button,
                    ],
                    spacing=SPACING.md,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row([self._message, self._check], spacing=SPACING.xs),
            ],
            spacing=SPACING.xs,
        )
        self.control = ft.Container(
            content=self._content,
            padding=ft.Padding.symmetric(vertical=SPACING.md),
        )
        self.sync(device)

    def sync(self, device: Device) -> None:
        self._device = device
        relay = garage_relay_visual(device)
        self._relay.set(relay.label, relay.icon, relay.tone)
        latest = device.last_pulse
        if (
            self._uncertain and latest is not None
            and latest.requested_at is not None
            and latest.requested_at != self._baseline
            and latest.status in {"succeeded", "failed", "expired"}
        ):
            self._uncertain = False
            self._operation_status = latest.status
            self._message.value = strings.pulse_status(
                latest.status, latest.error)
            self._message.color = theme.tone_color(
                Tone.OK if latest.status == "succeeded" else Tone.ERROR)
            self._message.visible = True
            self._check.visible = False

        visual = pulse_button_visual(
            device,
            operation_status=self._operation_status,
            busy=self._busy,
            uncertain=self._uncertain,
        )
        self._render(visual)
        self._message.visible = bool(self._message.value)
        capability = device.capability("pulse")
        self._reason.value = (
            capability.disabled_reason
            if capability is not None and not capability.enabled and capability.disabled_reason
            else self._message.value if self._uncertain else ""
        )
        self._reason.visible = bool(self._reason.value)

    def _render(self, visual: StateVisual) -> None:
        self._button.content = visual.label
        self._button.icon = icon_for(visual.icon)
        self._button.style = state_button_style(visual.tone)
        self._button.disabled = (
            not visual.enabled or self._on_pulse is None
            or self._busy or self._uncertain
        )
        if self._uncertain:
            self._check.visible = self._on_check is not None

    def _set_status(self, status: str, reason: str | None, request_id: str | None) -> None:
        self._operation_status = status
        self._message.value = strings.pulse_status(status, reason)
        self._message.visible = True
        self._message.color = theme.tone_color(
            Tone.WARNING if status in {"pending", "sent", "uncertain"}
            else Tone.ERROR if status in {"failed", "expired"}
            else Tone.OK if status == "succeeded"
            else Tone.MUTED
        )
        if status == "uncertain":
            self._uncertain = True
            self._check.visible = self._on_check is not None
        elif status in {"pending", "dispatching", "sent"}:
            self._uncertain = False
            self._check.visible = self._on_check is not None
        elif status in {"succeeded", "failed", "expired", "cancelled"}:
            self._uncertain = False
            self._check.visible = False
        self.sync(self._device)
        if self._page is not None:
            self._page.update()

    async def _pulse(self, _: ft.Event) -> None:
        if self._on_pulse is None or self._busy or self._uncertain:
            return
        visual = pulse_button_visual(self._device)
        if not visual.enabled:
            return
        self._baseline = (
            self._device.last_pulse.requested_at
            if self._device.last_pulse else None
        )
        self._busy = True
        self._operation_status = "pending"
        self._message.value = strings.PULSE_PENDING
        self._message.color = theme.tone_color(Tone.WARNING)
        self.sync(self._device)
        if self._page is not None:
            self._page.update()
        try:
            status = await self._on_pulse(
                self.device_id, self._baseline, self._set_status)
            self._operation_status = status
            if status == "uncertain":
                self._uncertain = True
                self._check.visible = self._on_check is not None
        except AmbiguousPulseResult as error:
            self._uncertain = True
            self._operation_status = "uncertain"
            self._message.value = strings.pulse_status("uncertain", str(error))
            self._message.color = theme.tone_color(Tone.WARNING)
            self._check.visible = self._on_check is not None
        except PulseRejected as error:
            self._operation_status = "failed"
            self._message.value = strings.pulse_status("failed", str(error))
            self._message.color = theme.tone_color(Tone.ERROR)
        except ApiError as error:
            self._uncertain = True
            self._operation_status = "uncertain"
            self._message.value = strings.pulse_status("uncertain", str(error))
            self._message.color = theme.tone_color(Tone.WARNING)
            self._check.visible = self._on_check is not None
        except Exception as error:
            logger.warning("Garage pulse flow failed: %s",
                           type(error).__name__)
            self._uncertain = True
            self._operation_status = "uncertain"
            self._message.value = strings.pulse_status("uncertain", None)
            self._message.color = theme.tone_color(Tone.WARNING)
            self._check.visible = self._on_check is not None
        finally:
            self._busy = False
            self.sync(self._device)
            if self._page is not None:
                self._page.update()

    async def _check_status(self, _: ft.Event) -> None:
        if self._on_check is None:
            return
        try:
            status = await self._on_check(
                self.device_id, self._baseline, self._set_status)
            if status in {"succeeded", "failed", "expired"}:
                self._uncertain = False
                self._operation_status = status
                self._check.visible = False
        except ApiError as error:
            self._message.value = strings.pulse_status("uncertain", str(error))
            self._message.color = theme.tone_color(Tone.WARNING)
        except Exception as error:
            logger.warning("Garage pulse status check failed: %s",
                           type(error).__name__)
            self._message.value = strings.pulse_status("uncertain", None)
            self._message.color = theme.tone_color(Tone.WARNING)
        self.sync(self._device)
        if self._page is not None:
            self._page.update()
