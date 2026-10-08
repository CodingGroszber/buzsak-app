"""Shared button shape and color styling for stateful controls (UX-13, UX-14)."""

from __future__ import annotations

import flet as ft

from buzsak_app.ui.theme import RADIUS, SPACING
from buzsak_app.ui.view_models import Tone


_STATES = {
    Tone.NEUTRAL: (ft.Colors.SECONDARY_CONTAINER, ft.Colors.ON_SECONDARY_CONTAINER),
    Tone.OK: (ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER),
    Tone.WARNING: (ft.Colors.TERTIARY_CONTAINER, ft.Colors.ON_TERTIARY_CONTAINER),
    Tone.ERROR: (ft.Colors.ERROR_CONTAINER, ft.Colors.ON_ERROR_CONTAINER),
    Tone.MUTED: (ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT),
}


def state_button_style(tone: Tone) -> ft.ButtonStyle:
    background, foreground = _STATES[tone]
    return ft.ButtonStyle(
        bgcolor=background,
        color=foreground,
        shape=ft.RoundedRectangleBorder(radius=RADIUS.chip),
        padding=ft.Padding.symmetric(
            horizontal=SPACING.sm, vertical=SPACING.sm),
        enable_feedback=True,
    )
