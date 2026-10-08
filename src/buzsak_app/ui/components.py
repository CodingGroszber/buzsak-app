"""Reusable Flet components. Each is built once and updated in place, not rebuilt (UPD-07)."""

from __future__ import annotations

import flet as ft

from buzsak_app.ui import theme
from buzsak_app.ui.theme import RADIUS, SPACING, TYPE
from buzsak_app.ui.view_models import Badge, HealthView, KpiView, Tone


def icon_for(name: str) -> ft.IconData:
    """Map a lower-case Material icon name to a Flet icon; unknown names get a generic one."""
    return getattr(ft.Icons, name.upper(), ft.Icons.SENSORS)


def _muted(size: int, **kwargs) -> ft.Text:
    return ft.Text(size=size, color=ft.Colors.ON_SURFACE_VARIANT, **kwargs)


class StatusChip:
    """Icon plus words, so a state is never conveyed by colour alone (UX-13)."""

    def __init__(self, text: str = "", icon: str = "sensors", tone: Tone = Tone.MUTED) -> None:
        self._icon = ft.Icon(icon_for(icon), size=TYPE.body)
        self._text = ft.Text(text, size=TYPE.caption,
                             weight=ft.FontWeight.W_600)
        self.control = ft.Row([self._icon, self._text],
                              spacing=SPACING.xs, tight=True)
        self.set(text, icon, tone)

    def set(self, text: str, icon: str, tone: Tone) -> None:
        color = theme.tone_color(tone)
        self._icon.icon = icon_for(icon)
        self._icon.color = color
        self._text.value = text
        self._text.color = color

    def set_badge(self, badge: Badge) -> None:
        self.set(badge.text, badge.icon, badge.tone)

    def set_health(self, health: HealthView) -> None:
        self.set(health.text, health.icon, health.tone)


class KpiCard:
    """One KPI: small uppercase label, big value with a smaller unit, state badge, caption (UX-10)."""

    def __init__(self) -> None:
        self._label_icon = ft.Icon(
            ft.Icons.SENSORS, size=TYPE.body, color=ft.Colors.ON_SURFACE_VARIANT)
        self._label = _muted(
            TYPE.label,
            weight=ft.FontWeight.W_600,
            style=ft.TextStyle(letter_spacing=theme.LABEL_LETTER_SPACING),
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self._value = ft.Text(
            size=TYPE.value, weight=ft.FontWeight.BOLD, no_wrap=True)
        self._unit = _muted(TYPE.unit)
        self._badge = StatusChip()
        self._caption = _muted(TYPE.caption, max_lines=2,
                               overflow=ft.TextOverflow.ELLIPSIS)

        self._value_row = ft.Row(
            [self._value, ft.Container(
                self._unit, padding=ft.Padding.only(bottom=SPACING.xs))],
            spacing=SPACING.xs,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )
        self._body = ft.Column(
            [
                ft.Row([self._label_icon, ft.Container(
                    self._label, expand=True)], spacing=SPACING.sm),
                self._value_row,
                self._badge.control,
                self._caption,
            ],
            spacing=SPACING.xs,
            animate_opacity=ft.Animation(
                theme.ANIMATION_MS, ft.AnimationCurve.EASE_OUT),
        )
        self.control = ft.Container(
            content=self._body,
            padding=ft.Padding.all(SPACING.md),
            height=theme.KPI_CARD_HEIGHT,
            border_radius=ft.BorderRadius.all(RADIUS.card),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            col={"xs": 6, "md": 4, "xl": 3},
        )

    def update_from(self, view: KpiView) -> None:
        self._label_icon.icon = icon_for(view.icon)
        self._label.value = view.label.upper()
        self._value.value = view.value_text
        # Words (a mode name) are wider than numbers, so they use the smaller size.
        self._value.size = TYPE.value_text if view.long_text else TYPE.value
        self._unit.value = view.unit or ""
        self._value_row.controls[1].visible = bool(view.unit)
        self._badge.control.visible = view.badge is not None
        if view.badge is not None:
            self._badge.set_badge(view.badge)
        self._caption.value = view.caption or ""
        self._caption.visible = bool(view.caption)
        self._body.opacity = theme.DIMMED_OPACITY if view.dimmed else 1.0
        # Shown on long-press on a touchscreen (DATA-04).
        self.control.tooltip = view.detail


def section_title(text: str) -> ft.Text:
    return ft.Text(text, size=TYPE.title, weight=ft.FontWeight.W_600)


def device_header(label: str, health_chip: StatusChip, detail: ft.Text) -> ft.Control:
    return ft.Column(
        [
            ft.Row(
                [section_title(label), health_chip.control],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            detail,
        ],
        spacing=SPACING.xs,
    )


def centered_message(text: str) -> ft.Control:
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding.all(SPACING.lg),
        content=ft.Text(text, color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER),
    )


def muted_text(text: str = "", size: int = TYPE.caption) -> ft.Text:
    return _muted(size, value=text)
