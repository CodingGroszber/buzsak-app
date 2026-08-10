"""Reusable UI helpers for tile and badge styling."""

from __future__ import annotations

import flet as ft

from app.constants import C_BORDER, C_DIM, C_DIM2, C_ON, C_SURFACE, C_WARN, C_ACCENT, C_AMBER


def border_all(width: int, color: str) -> ft.Border:
    """Create a rectangular border with identical side styles."""
    side = ft.BorderSide(width, color)
    return ft.Border(top=side, right=side, bottom=side, left=side)


def set_status_badge(box: ft.Container, txt: ft.Text, kind: str) -> None:
    """Apply badge colors for status types."""
    if kind == "on":
        txt.color = C_ON
        box.bgcolor = "#0d2518"
        box.border = border_all(1, "#1f5f3b")
    elif kind == "warn":
        txt.color = C_WARN
        box.bgcolor = "#2a1414"
        box.border = border_all(1, "#5a2323")
    elif kind == "accent":
        txt.color = C_ACCENT
        box.bgcolor = "#122035"
        box.border = border_all(1, "#24466e")
    elif kind == "amber":
        txt.color = C_AMBER
        box.bgcolor = "#2a2010"
        box.border = border_all(1, "#6a4f1f")
    else:
        txt.color = C_DIM
        box.bgcolor = "#1a1a1a"
        box.border = border_all(1, C_DIM2)


def make_status_badge(text: str, kind: str = "off") -> tuple[ft.Container, ft.Text]:
    """Create a compact status badge and initialize its visual state."""
    txt = ft.Text(text, size=10, weight=ft.FontWeight.BOLD)
    box = ft.Container(content=txt, padding=ft.Padding(
        6, 3, 6, 3), border_radius=4)
    set_status_badge(box, txt, kind)
    return box, txt


def make_tile(
    title: str,
    content: ft.Control,
    col: int = 6,
    title_size: int = 10,
    pad: int = 10,
    border_color: str = C_BORDER,
) -> ft.Container:
    """Create a section tile with responsive width and title."""
    return ft.Container(
        col={"xs": 12, "sm": col, "md": col, "lg": col},
        bgcolor=C_SURFACE,
        border=border_all(1, border_color),
        border_radius=6,
        padding=pad,
        content=ft.Column(
            [
                ft.Text(title, size=title_size, color=C_DIM,
                        weight=ft.FontWeight.BOLD),
                content,
            ],
            spacing=6,
        ),
    )


def io_tile(label: str, value: str, kind: str, sub: str | None = None) -> ft.Container:
    """Create one compact IO status tile for PLC output visualization."""
    badge_box, _badge_txt = make_status_badge(value, kind)
    items: list[ft.Control] = [
        ft.Text(label, size=10, color=C_DIM, no_wrap=True),
        badge_box,
    ]
    if sub:
        items.append(ft.Text(sub, size=10, color=C_DIM))
    return ft.Container(
        col={"xs": 12, "sm": 6, "md": 4, "lg": 3},
        bgcolor=C_SURFACE,
        border=border_all(1, C_BORDER),
        border_radius=5,
        padding=9,
        content=ft.Column(items, spacing=5),
    )
