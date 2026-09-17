"""Canvas-based dual-axis history chart for water level and pressure."""

from __future__ import annotations

import math
from datetime import datetime

import flet as ft
import flet.canvas as cv

try:
    from flet.controls.painting import Paint, PaintingStyle  # flet >=0.29
except ModuleNotFoundError:
    from flet.core.painting import Paint, PaintingStyle  # flet 0.28.x (Pi)

from app.constants import C_ACCENT, C_AMBER, C_DIM, C_DIM2, C_TEXT
from app.sensor_store import Row

_DEFAULT_W = 320
_H = 150
_PAD_L = 38
_PAD_R = 38
_PAD_T = 14
_PAD_B = 26

_C_GRID = "#222222"
_C_LEVEL = C_ACCENT      # water level line
_C_PRESSURE = C_AMBER    # pressure line
_PRESSURE_ALPHA = 0.2
_LEVEL_ALPHA = 0.03       # water level changes more slowly than pressure
_MAX_RENDER_POINTS = 120
# Vertical grid spacing picked by trailing span: (max span seconds, grid seconds).
_GRID_STEPS = (
    (2 * 3600, 10 * 60),
    (2 * 86400, 3 * 3600),
    (2 * 7 * 86400, 86400),
    (float("inf"), 7 * 86400),
)


def _line_paint(color: str, width: float = 2.0) -> Paint:
    return Paint(color=color, style=PaintingStyle.STROKE, stroke_width=width)


def _lowpass(rows: list[Row]) -> list[Row]:
    """Apply an exponential low-pass filter independently to both series."""
    previous_pressure: float | None = None
    previous_level: float | None = None
    filtered: list[Row] = []
    for ts, pressure, level in rows:
        if pressure is not None:
            previous_pressure = (
                pressure if previous_pressure is None else
                _PRESSURE_ALPHA * pressure +
                (1 - _PRESSURE_ALPHA) * previous_pressure
            )
        if level is not None:
            previous_level = (
                level if previous_level is None else
                _LEVEL_ALPHA * level + (1 - _LEVEL_ALPHA) * previous_level
            )
        filtered.append((ts, previous_pressure, previous_level))
    return filtered


def _grid_step_seconds(t_span: float) -> float:
    """Pick a readable vertical grid interval for the given trailing span."""
    for max_span, step in _GRID_STEPS:
        if t_span <= max_span:
            return step
    return _GRID_STEPS[-1][1]


def _axis_time_format(t_span: float) -> str:
    """Use a date format for multi-day spans, time-of-day otherwise."""
    return "%b %d" if t_span > 86400 else "%H:%M"


def _limit_render_points(rows: list[Row]) -> list[Row]:
    """Evenly reduce chart points without changing stored sensor history."""
    if len(rows) <= _MAX_RENDER_POINTS:
        return rows
    last_index = len(rows) - 1
    return [
        rows[round(index * last_index / (_MAX_RENDER_POINTS - 1))]
        for index in range(_MAX_RENDER_POINTS)
    ]


class SensorChartControl:
    """Renders water level (L) and pressure (bar) history on one canvas."""

    def __init__(self) -> None:
        self._width = _DEFAULT_W
        self._rows: list[Row] = []
        self._canvas = cv.Canvas(
            height=_H,
            shapes=[],
            expand=True,
            on_resize=self._on_resize,
        )
        legend = ft.Row(
            [
                ft.Container(width=10, height=10,
                             bgcolor=_C_LEVEL, border_radius=2),
                ft.Text("Water Level (L)", size=10, color=C_TEXT),
                ft.Container(width=10, height=10,
                             bgcolor=_C_PRESSURE, border_radius=2),
                ft.Text("Pressure (bar)", size=10, color=C_TEXT),
            ],
            spacing=6,
        )
        self.control = ft.Column(
            [self._canvas, legend],
            spacing=6,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._draw([])

    def update_data(self, rows: list[Row]) -> None:
        """Redraw the chart with the given (ts, pressure_bar, water_level_l) rows."""
        self._rows = rows
        self._draw(rows)

    def _on_resize(self, event: cv.CanvasResizeEvent) -> None:
        """Store the width assigned by the responsive parent."""
        width = max(float(event.width), _PAD_L + _PAD_R + 80)
        if width != self._width:
            self._width = width
            self._draw(self._rows)

    def _draw(self, rows: list[Row]) -> None:
        shapes: list[cv.Shape] = []
        plot_w = self._width - _PAD_L - _PAD_R
        plot_h = _H - _PAD_T - _PAD_B
        x0, y0 = _PAD_L, _PAD_T

        usable = _limit_render_points(_lowpass(
            [r for r in rows if r[1] is not None or r[2] is not None]
        ))

        times = [r[0] for r in usable]
        pressures = [r[1] for r in usable if r[1] is not None]
        levels = [r[2] for r in usable if r[2] is not None]
        t_min, t_max = (min(times), max(times)) if times else (0.0, 1.0)
        t_span = max(t_max - t_min, 1.0)
        p_min, p_max = (min(pressures), max(pressures)
                        ) if pressures else (0.0, 1.0)
        l_min, l_max = (min(levels), max(levels)) if levels else (0.0, 1.0)
        if p_max - p_min < 0.1:
            p_min, p_max = p_min - 0.5, p_max + 0.5
        if l_max - l_min < 1.0:
            l_min, l_max = l_min - 1.0, l_max + 1.0

        plot_bottom = y0 + plot_h
        plot_right = x0 + plot_w
        axis_paint = _line_paint(C_DIM2, 1.0)
        grid_paint = _line_paint(_C_GRID, 1.0)

        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = y0 + plot_h * (1.0 - fraction)
            shapes.append(cv.Line(x0, y, plot_right, y, grid_paint))
        grid_step = _grid_step_seconds(t_span)
        first_grid_ts = math.ceil(t_min / grid_step) * grid_step
        grid_ts = first_grid_ts
        while grid_ts < t_max:
            x = x0 + (grid_ts - t_min) / t_span * plot_w
            shapes.append(cv.Line(x, y0, x, plot_bottom, grid_paint))
            grid_ts += grid_step
        shapes.extend([
            cv.Line(x0, y0, x0, plot_bottom, axis_paint),
            cv.Line(plot_right, y0, plot_right, plot_bottom, axis_paint),
            cv.Line(x0, plot_bottom, plot_right, plot_bottom, axis_paint),
        ])

        def label(x: float, y: float, value: str, color: str = C_DIM) -> None:
            shapes.append(cv.Text(x, y, value,
                                  style=ft.TextStyle(size=8, color=color)))

        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = y0 + plot_h * (1.0 - fraction) - 5
            label(2, y, f"{l_min + (l_max - l_min) * fraction:.0f}", _C_LEVEL)
            label(plot_right + 4, y,
                  f"{p_min + (p_max - p_min) * fraction:.1f}", _C_PRESSURE)
        time_format = _axis_time_format(t_span)
        label(x0 - 4, plot_bottom + 7,
              datetime.fromtimestamp(t_min).strftime(time_format))
        label(plot_right - 24, plot_bottom + 7,
              datetime.fromtimestamp(t_max).strftime(time_format))
        shapes.append(cv.Text(1, y0 + plot_h / 2 + 20, "L", rotate=270,
                              style=ft.TextStyle(size=9, color=_C_LEVEL)))
        shapes.append(cv.Text(plot_right + 18, y0 + plot_h / 2 + 24, "bar", rotate=270,
                              style=ft.TextStyle(size=9, color=_C_PRESSURE)))

        if len(usable) < 2:
            shapes.append(cv.Text(
                x0 + plot_w / 2 - 30,
                y0 + plot_h / 2 - 6,
                "No data yet",
                style=ft.TextStyle(size=11, color=C_DIM2),
            ))
            self._canvas.shapes = shapes
            return

        def x_at(ts: float) -> float:
            return x0 + (ts - t_min) / t_span * plot_w

        def y_level(value: float) -> float:
            return y0 + plot_h - (value - l_min) / (l_max - l_min) * plot_h

        def y_pressure(value: float) -> float:
            return y0 + plot_h - (value - p_min) / (p_max - p_min) * plot_h

        prev_level_pt: tuple[float, float] | None = None
        prev_pressure_pt: tuple[float, float] | None = None
        for ts, pressure, level in usable:
            x = x_at(ts)
            if level is not None:
                y = y_level(level)
                if prev_level_pt is not None:
                    shapes.append(
                        cv.Line(*prev_level_pt, x, y, _line_paint(_C_LEVEL)))
                prev_level_pt = (x, y)
            if pressure is not None:
                y = y_pressure(pressure)
                if prev_pressure_pt is not None:
                    shapes.append(
                        cv.Line(*prev_pressure_pt, x, y, _line_paint(_C_PRESSURE)))
                prev_pressure_pt = (x, y)

        self._canvas.shapes = shapes


__all__ = ["SensorChartControl"]
