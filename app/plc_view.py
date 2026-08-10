"""PLC data extraction and UI rendering helpers."""

from __future__ import annotations

import flet as ft

from app.constants import C_DIM, C_TEXT


def pick_metric(source: dict, names: list[str]):
    """Search common top-level and nested containers for a metric value."""
    containers = [source]
    for key in ("sensors", "metrics", "status", "plc", "data"):
        nested = source.get(key)
        if isinstance(nested, dict):
            containers.append(nested)

    for container in containers:
        for name in names:
            if name in container and container[name] is not None:
                return container[name]
    return "--"


def pick_analog_metric(source: dict, metric_name: str, value_keys: list[str]):
    """Find a named analog item and read first available value key."""
    analog = source.get("analog")
    if not isinstance(analog, list):
        return "--"

    for item in analog:
        if not isinstance(item, dict):
            continue
        if str(item.get("name", "")).lower() != metric_name.lower():
            continue
        for key in value_keys:
            value = item.get(key)
            if value is not None:
                return value
    return "--"


def render_meta_tiles(data: dict, make_tile, meta_row: ft.ResponsiveRow):
    """Render water level and pressure metric tiles."""
    water_level = pick_analog_metric(
        data, "water_level", ["liters", "value", "level"])
    if water_level == "--":
        water_level = pick_metric(
            data,
            ["water_level", "waterLevel", "tank_level", "tankLevel", "level"],
        )

    pressure = pick_analog_metric(
        data, "pressure", ["bar", "value", "pressure"])
    if pressure == "--":
        pressure = pick_metric(
            data,
            ["pressure", "pressure_bar", "pressureBar", "plc_pressure"],
        )

    water_text = f"{water_level} L" if water_level != "--" else "--"
    pressure_text = f"{pressure} bar" if pressure != "--" else "--"

    meta_row.controls = [
        make_tile(
            "Water Level",
            ft.Text(water_text, size=17, color=C_TEXT,
                    weight=ft.FontWeight.BOLD),
            col=6,
        ),
        make_tile(
            "Pressure",
            ft.Text(pressure_text, size=17, color=C_TEXT,
                    weight=ft.FontWeight.BOLD),
            col=6,
        ),
    ]


def render_io_tiles(
    data: dict,
    blink_on: bool,
    outputs_row: ft.ResponsiveRow,
    io_tile,
    sw_right_box: ft.Container,
    sw_right_txt: ft.Text,
    sw_left_box: ft.Container,
    sw_left_txt: ft.Text,
    set_status_badge,
):
    """Render switch status and PLC outputs using existing observed mapping."""
    inputs = data.get("inputs", [])
    outputs = data.get("outputs", [])

    raw_right_sw = False
    raw_left_sw = False
    for inp in inputs:
        name = str(inp.get("name", "")).lower()
        if name == "right_sw":
            raw_right_sw = bool(inp.get("state"))
        elif name == "left_sw":
            raw_left_sw = bool(inp.get("state"))

    # On this PLC image, selector contact names are physically inverted.
    if raw_left_sw != raw_right_sw:
        right_auto = raw_left_sw
        left_well_pump = raw_right_sw
    else:
        right_auto = raw_right_sw
        left_well_pump = raw_left_sw

    sw_right_txt.value = "AUTO" if right_auto else "MANUAL"
    set_status_badge(sw_right_box, sw_right_txt, "on" if right_auto else "off")

    if left_well_pump:
        sw_left_txt.value = "WELL PUMP ACTIVE"
        set_status_badge(sw_left_box, sw_left_txt,
                         "amber" if blink_on else "off")
    else:
        sw_left_txt.value = "IDLE"
        set_status_badge(sw_left_box, sw_left_txt, "off")

    outputs_row.controls = []
    for out in outputs:
        out_name = str(out.get("name", "")).lower()
        out_label = str(out.get("label", "")).lower()
        if out_name in {"switch_led", "wifi_led"}:
            continue
        if "switch led" in out_label or "wifi led" in out_label:
            continue

        is_on = bool(out.get("state"))
        outputs_row.controls.append(
            io_tile(
                str(out.get("label", out.get("name", "OUTPUT"))),
                "ON" if is_on else "OFF",
                "on" if is_on else "off",
            )
        )


__all__ = ["render_meta_tiles", "render_io_tiles",
           "pick_metric", "pick_analog_metric"]
