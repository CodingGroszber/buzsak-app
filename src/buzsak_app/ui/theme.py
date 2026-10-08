"""Design tokens and Material 3 themes; views must not hard-code styles (UX-13..UX-17)."""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from buzsak_app.ui.view_models import Tone

# The single accent colour (UX-13); Material 3 derives the rest of the scheme from it.
ACCENT = "#2E7D5B"

# Warning amber, chosen per brightness for WCAG AA contrast on the surface (UX-15):
# about 5.4:1 on white in light mode and about 10:1 on near-black in dark mode.
WARNING_LIGHT = "#9A5B00"
WARNING_DARK = "#FFB74D"


@dataclass(frozen=True)
class Spacing:
    xs: int = 4
    sm: int = 8
    md: int = 16
    lg: int = 24
    xl: int = 32


@dataclass(frozen=True)
class Radius:
    card: int = 16
    chip: int = 8


@dataclass(frozen=True)
class TypeScale:
    label: int = 11
    caption: int = 12
    body: int = 14
    unit: int = 14
    title: int = 18
    value: int = 32
    # Words such as "Automatic" are too wide for the numeric size on a half-width card.
    value_text: int = 22


SPACING = Spacing()
RADIUS = Radius()
TYPE = TypeScale()

LABEL_LETTER_SPACING = 1.2
DIMMED_OPACITY = 0.55
# One height for every KPI card keeps the grid tidy whether or not a card has a caption.
KPI_CARD_HEIGHT = 156
# Subtle value changes only; at most 250 ms (UPD-07).
ANIMATION_MS = 200

_TONE_COLORS: dict[Tone, str] = {
    Tone.NEUTRAL: ft.Colors.ON_SURFACE,
    Tone.OK: ft.Colors.PRIMARY,
    Tone.WARNING: ft.Colors.TERTIARY,
    Tone.ERROR: ft.Colors.ERROR,
    Tone.MUTED: ft.Colors.ON_SURFACE_VARIANT,
}


def tone_color(tone: Tone) -> str:
    return _TONE_COLORS[tone]


def app_theme(*, dark: bool) -> ft.Theme:
    """Seeded Material 3 theme; `tertiary` carries the warning tone."""
    return ft.Theme(
        color_scheme_seed=ACCENT,
        use_material3=True,
        color_scheme=ft.ColorScheme(
            tertiary=WARNING_DARK if dark else WARNING_LIGHT),
    )
