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
from buzsak_app.ui.theme import SPACING
from buzsak_app.ui.view_models import device_detail, health_view, kpi_view, sorted_parameters

# The mode decides whether automation values are frozen, so a mode change refreshes the whole device.
_MODE = "mode"


class _DeviceSection:
    def __init__(self, device: Device, *, greenhouse: GreenhouseControls | None = None) -> None:
        self.device_id = device.id
        self._label = device.label
        self._health = StatusChip()
        self._detail = muted_text()
        self._grid = ft.ResponsiveRow(
            spacing=SPACING.sm, run_spacing=SPACING.sm)
        self._cards: dict[str, KpiCard] = {}
        self._order: list[str] = []
        self._greenhouse = greenhouse
        contents = [device_header(device.label, self._health, self._detail)]
        if greenhouse is not None:
            contents.append(greenhouse.control)
        contents.append(self._grid)
        body = ft.Column(
            contents,
            spacing=SPACING.md,
        )
        if greenhouse is not None:
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
        parameters = sorted_parameters(device)
        if self._greenhouse is not None:
            handled = self._greenhouse._readings.handled_parameter_ids
            parameters = [
                parameter for parameter in parameters if parameter.id not in handled]
        order = [p.id for p in parameters]
        if order != self._order:
            # New or removed parameters: keep existing cards, create the rest.
            self._cards = {pid: self._cards.get(
                pid) or KpiCard() for pid in order}
            self._grid.controls = [self._cards[pid].control for pid in order]
            self._order = order
            changed = None
        if header:
            health = health_view(device)
            self._health.set_health(health)
            detail = device_detail(device)
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
    ) -> None:
        self.party_id = party.id
        self._sections: dict[str, _DeviceSection] = {}
        if not party.configured:
            self.control: ft.Control = centered_message(
                party.note or strings.PARTY_NOT_CONFIGURED)
        elif not party.devices:
            self.control = centered_message(strings.PARTY_NO_DEVICES)
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
                sections.append(_DeviceSection(device, greenhouse=greenhouse))
            self._sections = {s.device_id: s for s in sections}
            self.control = ft.Column(
                [s.control for s in sections],
                spacing=SPACING.lg,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            )
            self.control = ft.Container(
                content=self.control, padding=ft.Padding.all(SPACING.md), expand=True)

    def apply(self, party: Party, diff: SnapshotDiff) -> None:
        for device in party.devices:
            section = self._sections.get(device.id)
            if section is None:
                continue
            changed = frozenset(
                pid for did, pid in diff.changed_parameters if did == device.id)
            header = device.id in diff.changed_devices
            if changed or header:
                section.sync(device, changed=changed, header=header)
