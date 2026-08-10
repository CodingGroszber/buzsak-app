"""Safety arm control: horizontal 4-dot unlock pattern."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft
import flet.canvas as cv

try:
    from flet.controls.painting import Paint, PaintingStyle  # flet >=0.29
except ModuleNotFoundError:
    from flet.core.painting import Paint, PaintingStyle  # flet 0.28.x (Pi)

from app.constants import C_ON


def _event_local_x(e: ft.DragStartEvent | ft.DragUpdateEvent) -> float:
    # Flet 0.28.x stores local_x directly; 0.29+ uses local_position.x
    lp = getattr(e, "local_position", None)
    return lp.x if lp is not None else getattr(e, "local_x", 0.0)


# --- geometry -----------------------------------------------------------------
_W: int = 300           # canvas width (px)
_H: int = 56            # canvas height (px)
_CY: int = _H // 2      # vertical centre
_R: int = 15            # dot radius
# 4 dot centres, evenly distributed with padding
_PX: list[int] = [35, 112, 189, 266]
_HIT: int = 22          # px to the left of a dot centre to count as "reached"

# --- colours ------------------------------------------------------------------
_C_OFF = "#3a3a3a"
_C_ON = C_ON            # "#22c55e"
_C_LINE = "#222222"


def _paint(color: str, *, stroke: bool = False, width: float = 2.5) -> Paint:
    return Paint(
        color=color,
        style=PaintingStyle.STROKE if stroke else PaintingStyle.FILL,
        stroke_width=width,
    )


class DotUnlockControl:
    """4-dot horizontal pattern lock for the remote arm safety control.

    Drag left-to-right through all 4 dots in sequence to arm.
    Any incomplete release, backward drag, or new touch while armed disarms.
    """

    def __init__(self, on_arm: Callable[[bool], None], page: ft.Page) -> None:
        self._on_arm = on_arm
        self._page = page
        self.active: bool = False   # True = armed
        self._tracking: bool = False
        self._lit: int = 0          # dots currently lit in this drag

        self._canvas = cv.Canvas(width=_W, height=_H, shapes=[])
        self.control = ft.GestureDetector(
            content=self._canvas,
            # horizontal_drag is exclusive on mobile, preventing scroll from stealing the gesture
            on_horizontal_drag_start=self._start,
            on_horizontal_drag_update=self._update,
            on_horizontal_drag_end=self._end,
            mouse_cursor=ft.MouseCursor.GRAB,
        )
        self._draw(0)

    # --- drawing --------------------------------------------------------------

    def _draw(self, lit: int) -> None:
        shapes = []

        # Background connector line
        shapes.append(cv.Line(_PX[0], _CY, _PX[-1], _CY,
                              _paint(_C_LINE, stroke=True, width=3)))

        # Active connector line (grows right as dots are lit)
        if lit > 1:
            shapes.append(cv.Line(_PX[0], _CY, _PX[lit - 1], _CY,
                                  _paint(_C_ON, stroke=True, width=3)))

        for i, x in enumerate(_PX):
            on = i < lit
            # Outer ring
            shapes.append(cv.Circle(x, _CY, _R,
                                    _paint(_C_ON if on else _C_OFF,
                                           stroke=True, width=2)))
            # Inner fill when active
            if on:
                shapes.append(cv.Circle(x, _CY, _R - 5, _paint(_C_ON)))

        self._canvas.shapes = shapes

    # --- gesture handlers -----------------------------------------------------

    def _start(self, e: ft.DragStartEvent) -> None:
        if self.active:
            # Any new touch while armed immediately disarms (deadman safety)
            self._tracking = False
            self._lit = 0
            self.active = False
            self._draw(0)
            self._on_arm(False)
            self._page.update()
            return

        # Only begin tracking when the drag starts near dot 0
        if abs(_event_local_x(e) - _PX[0]) <= _R * 1.5:
            self._tracking = True
            self._lit = 1
            self._draw(1)
            self._page.update()

    def _update(self, e: ft.DragUpdateEvent) -> None:
        if not self._tracking:
            return
        x = _event_local_x(e)

        # Backward drag cancels the gesture
        if x < _PX[0] - _R:
            self._tracking = False
            self._lit = 0
            self._draw(0)
            self._page.update()
            return

        # Sequential activation: stop at the first gap
        new_lit = 1
        for i in range(1, 4):
            if x >= _PX[i] - _HIT:
                new_lit = i + 1
            else:
                break

        if new_lit != self._lit:
            self._lit = new_lit
            self._draw(new_lit)
            self._page.update()

    def _end(self, _e: ft.DragEndEvent) -> None:
        if not self._tracking:
            return
        self._tracking = False

        if self._lit >= 4:
            self.active = True
            self._draw(4)
            self._on_arm(True)
        else:
            self._lit = 0
            self._draw(0)

        self._page.update()
