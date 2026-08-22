"""Canvas-based dual-axis history chart for water level and pressure."""

from __future__ import annotations

import flet as ft
import flet.canvas as cv

try:
    from flet.controls.painting import Paint, PaintingStyle  # flet >=0.29
except ModuleNotFoundError:
    from flet.core.painting import Paint, PaintingStyle  # flet 0.28.x (Pi)

from app.constants import C_ACCENT, C_AMBER, C_DIM2, C_TEXT
from app.sensor_store import Row

_W = 320
_H = 150
_PAD_L = 8
_PAD_R = 8
_PAD_T = 10
_PAD_B = 18

_C_GRID = "#222222"
_C_LEVEL = C_ACCENT      # water level line
_C_PRESSURE = C_AMBER    # pressure line


def _line_paint(color: str, width: float = 2.0) -> Paint:
    return Paint(color=color, style=PaintingStyle.STROKE, stroke_width=width)


class SensorChartControl:
    """Renders water level (L) and pressure (bar) history on one canvas."""

    def __init__(self) -> None:
        self._canvas = cv.Canvas(width=_W, height=_H, shapes=[])
        legend = ft.Row(
            [
                ft.Container(width=10, height=10, bgcolor=_C_LEVEL, border_radius=2),
                ft.Text("Water Level (L)", size=10, color=C_TEXT),
                ft.Container(width=10, height=10, bgcolor=_C_PRESSURE, border_radius=2),
                ft.Text("Pressure (bar)", size=10, color=C_TEXT),
            ],
            spacing=6,
        )
        self.control = ft.Column([self._canvas, legend], spacing=6)
        self._draw([])

    def update_data(self, rows: list[Row]) -> None:
        """Redraw the chart with the given (ts, pressure_bar, water_level_l) rows."""
        self._draw(rows)

    def _draw(self, rows: list[Row]) -> None:
        shapes: list[cv.Shape] = []
        plot_w = _W - _PAD_L - _PAD_R
        plot_h = _H - _PAD_T - _PAD_B
        x0, y0 = _PAD_L, _PAD_T

        shapes.append(cv.Line(x0, y0 + plot_h, x0 + plot_w, y0 +
                      plot_h, _line_paint(_C_GRID, 1)))

        usable = [r for r in rows if r[1] is not None or r[2] is not None]
        if len(usable) < 2:
            shapes.append(
                cv.Text(
                    x0 + plot_w / 2 - 30,
                    y0 + plot_h / 2 - 6,
                    "No data yet",
                    style=ft.TextStyle(size=11, color=C_DIM2),
                )
            )
            self._canvas.shapes = shapes
            return

        times = [r[0] for r in usable]
        pressures = [r[1] for r in usable if r[1] is not None]
        levels = [r[2] for r in usable if r[2] is not None]

        t_min, t_max = min(times), max(times)
        t_span = max(t_max - t_min, 1.0)

        p_min, p_max = (min(pressures), max(pressures)) if pressures else (0.0, 1.0)
        if p_max - p_min < 0.1:
            p_min, p_max = p_min - 0.5, p_max + 0.5

        l_min, l_max = (min(levels), max(levels)) if levels else (0.0, 1.0)
        if l_max - l_min < 1.0:
            l_min, l_max = l_min - 1.0, l_max + 1.0

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
