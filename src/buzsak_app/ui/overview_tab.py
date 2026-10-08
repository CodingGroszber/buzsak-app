"""Overview tab: one tappable card per party with health and headline KPIs (UX-03)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from buzsak_app.domain.models import Device, Party, Snapshot
from buzsak_app.domain.presentation import HEADLINE_PARAMETERS
from buzsak_app.ui import strings, theme
from buzsak_app.ui.components import StatusChip, centered_message, muted_text, section_title
from buzsak_app.ui.theme import RADIUS, SPACING, TYPE
from buzsak_app.ui.view_models import device_detail, health_view, kpi_view

SelectParty = Callable[[str], Awaitable[None]]


def _headline_row(device: Device, parameter_id: str) -> ft.Control | None:
    parameter = device.parameter(parameter_id)
    if parameter is None:
        return None
    view = kpi_view(device, parameter)
    value = f"{view.value_text} {view.unit}" if view.unit else view.value_text
    cells: list[ft.Control] = [
        ft.Text(view.label, size=TYPE.body,
                color=ft.Colors.ON_SURFACE_VARIANT, expand=True),
        ft.Text(value, size=TYPE.body, weight=ft.FontWeight.BOLD),
    ]
    if view.badge is not None:
        chip = StatusChip()
        chip.set_badge(view.badge)
        cells.append(chip.control)
    return ft.Row(cells, spacing=SPACING.sm, opacity=theme.DIMMED_OPACITY if view.dimmed else 1.0)


def _device_block(device: Device) -> ft.Control:
    chip = StatusChip()
    chip.set_health(health_view(device))
    header = ft.Row(
        [ft.Text(device.label, size=TYPE.body,
                 weight=ft.FontWeight.W_600, expand=True), chip.control],
        spacing=SPACING.sm,
    )
    rows: list[ft.Control] = [header]
    if (detail := device_detail(device)) is not None:
        rows.append(muted_text(detail))
    rows.extend(row for pid in HEADLINE_PARAMETERS if (
        row := _headline_row(device, pid)) is not None)
    return ft.Column(rows, spacing=SPACING.xs)


class OverviewTab:
    """Rebuilt wholesale on change: it is small and not scroll-sensitive."""

    def __init__(self, on_select: SelectParty) -> None:
        self._on_select = on_select
        self._column = ft.Column(
            spacing=SPACING.md, scroll=ft.ScrollMode.AUTO, expand=True)
        self._empty = centered_message(strings.NO_DATA_YET)
        self.control = ft.Container(
            content=self._empty, padding=ft.Padding.all(SPACING.md), expand=True)
        self._has_cards = False

    def refresh(self, snapshot: Snapshot | None) -> None:
        if snapshot is None or not snapshot.parties:
            self.control.content = self._empty
            self._has_cards = False
            return
        self._column.controls = [self._party_card(p) for p in snapshot.parties]
        if not self._has_cards:
            self.control.content = self._column
            self._has_cards = True

    def _party_card(self, party: Party) -> ft.Control:
        body: list[ft.Control] = [
            ft.Row(
                [section_title(strings.party_title(party.id, party.label)), ft.Icon(
                    ft.Icons.CHEVRON_RIGHT)],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            )
        ]
        if not party.configured:
            body.append(muted_text(party.note or strings.PARTY_NOT_CONFIGURED))
        elif not party.devices:
            body.append(muted_text(strings.PARTY_NO_DEVICES))
        for device in party.devices:
            body.append(ft.Divider(height=1))
            body.append(_device_block(device))

        async def tapped(_: ft.Event) -> None:
            await self._on_select(party.id)

        return ft.Container(
            content=ft.Column(body, spacing=SPACING.sm),
            padding=ft.Padding.all(SPACING.md),
            border_radius=ft.BorderRadius.all(RADIUS.card),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            ink=True,
            on_click=tapped,
        )
