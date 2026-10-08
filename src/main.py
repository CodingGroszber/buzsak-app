"""Flet entry point (ARC-02). Kept thin: all logic lives in the `buzsak_app` package."""

from __future__ import annotations

import flet as ft

from buzsak_app.ui.app import main

if __name__ == "__main__":
    ft.run(main)
