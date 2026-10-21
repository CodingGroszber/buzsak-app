"""A party tab: one section per device with KPI cards, updated in place (UX-01, UX-02, UPD-07)."""

from __future__ import annotations

import flet as ft

from buzsak_app.domain.models import Device, Party
from buzsak_app.state.diff import SnapshotDiff
from buzsak_app.ui import strings
from buzsak_app.ui.components import (
    KpiCard,
    StatusChip,
    centered_message,
    device_header,
    muted_text,
)
from buzsak_app.ui.greenhouse_controls import CommandHandler, CommandLookup, GreenhouseControls
from buzsak_app.ui.garage_controls import GaragePulseControl, PulseHandler, PulseLookup
from buzsak_app.ui.pump_controls import PumpControls
from buzsak_app.ui.theme import SPACING
from buzsak_app.ui.view_models import device_detail, device_identity, health_view, kpi_view, sorted_parameters

# The mode decides whether automation values are frozen, so a mode change refreshes the whole device.
_MODE = "mode"


class _DeviceSection:
    def __init__(
        self,
        device: Device,
        *,
        greenhouse: GreenhouseControls | None = None,
        garage: GaragePulseControl | None = None,
        pump: PumpControls | None = None,
    ) -> None:
        self.device_id = device.id
        self._label = device.label
        self._health = StatusChip()
        self._detail = muted_text()
        self._grid = ft.ResponsiveRow(
            spacing=SPACING.sm, run_spacing=SPACING.sm)
        self._cards: dict[str, KpiCard] = {}
        self._order: list[str] = []
        self._greenhouse = greenhouse
        self._garage = garage
        self._pump = pump
        if pump is not None or greenhouse is not None:
            self._detail.expand = True
            heading = ft.Row(
                [self._detail, self._health.control], spacing=SPACING.sm,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        else:
            heading = device_header(device.label, self._health, self._detail)
        contents = [heading]
        if greenhouse is not None:
            contents.append(greenhouse.control)
        if garage is not None:
            contents.append(garage.control)
        if pump is not None:
            contents.append(pump.control)
        contents.append(self._grid)
        body = ft.Column(
            contents,
            spacing=SPACING.md,
            tight=True,
        )
        if greenhouse is not None or garage is not None or pump is not None:
            self.control = ft.ResponsiveRow(
                [ft.Container(
                    content=body,
                    col={"xs": 12, "md": 8, "lg": 6, "xl": 5},
                )],
                spacing=0,
                run_spacing=0,
            )
        else:
            self.control = body
        self.sync(device, changed=None, header=True)

    def sync(self, device: Device, *, changed: frozenset[str] | None, header: bool) -> None:
        """`changed` is the set of parameter ids to refresh; None refreshes all."""
        if self._greenhouse is not None:
            self._greenhouse.sync(device)
        if self._garage is not None:
            self._garage.sync(device)
        if self._pump is not None:
            self._pump.sync(device, changed=changed)
        parameters = sorted_parameters(device)
        if self._greenhouse is not None:
            handled = self._greenhouse._readings.handled_parameter_ids
            parameters = [
                parameter for parameter in parameters if parameter.id not in handled]
        if self._pump is not None:
            parameters = [parameter for parameter in parameters
                          if parameter.id not in self._pump.handled_parameter_ids]
        order = [p.id for p in parameters]
        self._grid.visible = bool(order)
        if order != self._order:
            # New or removed parameters: keep existing cards, create the rest.
            self._cards = {pid: self._cards.get(
                pid) or KpiCard() for pid in order}
            self._grid.controls = [self._cards[pid].control for pid in order]
            self._order = order
            changed = None
        if header or ((self._pump is not None or self._greenhouse is not None) and (
            changed is None or bool({"firmware", "ip"} & changed)
        )):
            health = health_view(device)
            self._health.set_health(health)
            detail = device_detail(device)
            if self._pump is not None or self._greenhouse is not None:
                detail = " | ".join(part for part in (
                    detail, device_identity(device)) if part)
            self._detail.value = detail or ""
            self._detail.visible = detail is not None
        refresh_all = changed is None or _MODE in changed
        for parameter in parameters:
            if refresh_all or parameter.id in changed:
                self._cards[parameter.id].update_from(
                    kpi_view(device, parameter))


class PartyTab:
    def __init__(
        self,
        party: Party,
        *,
        page: ft.Page | None = None,
        on_command: CommandHandler | None = None,
        on_check_command: CommandLookup | None = None,
        on_pulse: PulseHandler | None = None,
        on_check_pulse: PulseLookup | None = None,
    ) -> None:
        self.party_id = party.id
        self._sections: dict[str, _DeviceSection] = {}
        self._garage_controls: dict[str, GaragePulseControl] = {}
        if not party.configured:
            self.control: ft.Control = centered_message(
                party.note or strings.PARTY_NOT_CONFIGURED)
        elif not party.devices:
            self.control = centered_message(strings.PARTY_NO_DEVICES)
        elif party.kind == "matter" and any(
            device.id in {"sonoff-1", "sonoff-2"} for device in party.devices
        ):
            devices = [
                device for device in party.devices
                if device.id in {"sonoff-1", "sonoff-2"}
            ]
            self._garage_controls = {
                device.id: GaragePulseControl(
                    device, page=page, on_pulse=on_pulse,
                    on_check=on_check_pulse,
                )
                for device in devices
            }
            rows: list[ft.Control] = []
            for index, device in enumerate(devices):
                if index:
                    rows.append(ft.Divider(height=1))
                rows.append(self._garage_controls[device.id].control)
            self.control = ft.Container(
                content=ft.Column(rows, spacing=0),
                padding=ft.Padding.all(SPACING.md),
                expand=True,
            )
        else:
            sections = []
            for device in party.devices:
                greenhouse = (
                    GreenhouseControls(
                        device, page=page, on_command=on_command,
                        on_check_command=on_check_command,
                    )
                    if party.kind == "valve_controller" else None
                )
                pump = (
                    PumpControls(device, page=page, on_command=on_command,
                                 on_check_command=on_check_command)
                    if party.kind == "garden_plc" else None
                )
                sections.append(_DeviceSection(
                    device, greenhouse=greenhouse, pump=pump))
            self._sections = {s.device_id: s for s in sections}
            self.control = ft.Column(
                [s.control for s in sections],
                spacing=SPACING.lg,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
            self.control = ft.Container(
                content=self.control, padding=ft.Padding.all(SPACING.md), expand=True)

    def set_connection_available(self, available: bool) -> None:
        """Propagate server freshness to PLC controls without altering readings (CTL-12)."""
        for section in self._sections.values():
            if section._pump is not None:
                section._pump.set_available(available)

    def apply(self, party: Party, diff: SnapshotDiff) -> None:
        for device in party.devices:
            garage = self._garage_controls.get(device.id)
            if garage is not None and (
                device.id in diff.changed_devices
                or any(did == device.id for did, _ in diff.changed_parameters)
            ):
                garage.sync(device)
            section = self._sections.get(device.id)
            if section is None:
                continue
            changed = frozenset(
                pid for did, pid in diff.changed_parameters if did == device.id)
            header = device.id in diff.changed_devices
            if changed or header:
                section.sync(device, changed=changed, header=header)
