import asyncio
import json
import threading
import time

import flet as ft
import requests
import websocket

PLC_DIRECT_URL = "http://192.168.1.94/api/state"

TIMEOUT_DIRECT = 0.4
POLL_DIRECT = 0.5
POLL_MATTER = 1.0
UI_TICK = 0.35

# Prefer local loopback on the Pi; fallback to LAN IP if network routes shift.
MATTER_WS_URLS = (
    "ws://127.0.0.1:5580/ws",
    "ws://192.168.1.95:5580/ws",
)
MATTER_TIMEOUT = 2.0
MATTER_CONNECT_RETRIES = 2
MATTER_FAILS_TO_OFFLINE = 3
MATTER_ENDPOINT_ID = 1
MATTER_ONOFF_CLUSTER = 6
MATTER_PULSE_SECONDS = 0.5

MATTER_DOORS = {
    "right": {"label": "GARAGE RIGHT", "node_id": 1},
    "left": {"label": "GARAGE LEFT", "node_id": 3},
}

# Visual theme aligned with Garden PLC HTML.
C_BG = "#0c0c0c"
C_SURFACE = "#141414"
C_BORDER = "#222222"
C_TEXT = "#d4d4d4"
C_DIM = "#555555"
C_DIM2 = "#3a3a3a"
C_ON = "#22c55e"
C_WARN = "#ef4444"
C_ACCENT = "#3b82f6"
C_AMBER = "#f59e0b"


def main(page: ft.Page):
    page.title = "Buzsak Auto Home"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = C_BG
    page.padding = 12

    _st = {
        "d_ok": False,
        "d_ms": 0,
        "d_data": None,
        "d_err": "",
        "mr_ok": False,
        "mr_ms": 0,
        "mr_on": False,
        "mr_err": "",
        "ml_ok": False,
        "ml_ms": 0,
        "ml_on": False,
        "ml_err": "",
        "changed": True,
    }
    _lock = threading.Lock()
    _remote_active = [False]
    _matter_last_url = [MATTER_WS_URLS[0]]

    def border_all(width: int, color: str) -> ft.Border:
        s = ft.BorderSide(width, color)
        return ft.Border(top=s, right=s, bottom=s, left=s)

    def key_prefix(side: str) -> str:
        return "mr" if side == "right" else "ml"

    def make_status_badge(text: str, kind: str = "off") -> tuple[ft.Container, ft.Text]:
        txt = ft.Text(text, size=10, weight=ft.FontWeight.BOLD)
        box = ft.Container(content=txt, padding=ft.Padding(
            6, 3, 6, 3), border_radius=4)
        set_status_badge(box, txt, kind)
        return box, txt

    def set_status_badge(box: ft.Container, txt: ft.Text, kind: str):
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

    def make_tile(
        title: str,
        content: ft.Control,
        col: int = 6,
        title_size: int = 10,
        pad: int = 10,
        border_color: str = C_BORDER,
    ) -> ft.Container:
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
        badge_box, badge_txt = make_status_badge(value, kind)
        items = [
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

    header_dot = ft.Container(
        width=8, height=8, border_radius=4, bgcolor=C_WARN)
    header_matter_dot = ft.Container(
        width=8, height=8, border_radius=4, bgcolor=C_WARN)
    header_plc_ip = ft.Text("PLC: connecting...", size=11, color=C_DIM)
    header_matter_ip = ft.Text("Matter: 127.0.0.1:5580", size=11, color=C_DIM)
    header_fw = ft.Text("v--", size=11, color=C_DIM)
    header_latency = ft.Text("-- ms", size=10, color=C_DIM)
    err_text = ft.Text("", size=11, color=C_WARN, visible=False)

    rc_label = ft.Text("REMOTE ARM", size=11, color=C_TEXT,
                       weight=ft.FontWeight.BOLD)
    rc_slider = ft.Slider(
        min=0,
        max=100,
        value=0,
        divisions=100,
        active_color="#2f3f33",
        inactive_color="#2b2b2b",
        thumb_color="#ffffff",
        expand=True,
    )
    arm_badge_box, arm_badge_txt = make_status_badge("LOCKED", "off")

    door_refs: dict[str, dict[str, ft.Control]] = {}
    door_tiles_row = ft.ResponsiveRow(spacing=6, run_spacing=6)

    for side, cfg in MATTER_DOORS.items():
        state_box, state_txt = make_status_badge("OFFLINE", "warn")
        activate_btn = ft.FilledButton(
            "ACTIVATE",
            style=ft.ButtonStyle(
                bgcolor="#1f3a5f",
                color="#e8f1ff",
                shape=ft.RoundedRectangleBorder(radius=4),
            ),
            disabled=True,
        )
        hint = ft.Text("Slide REMOTE ARM to enable", size=10, color=C_DIM)
        latency = ft.Text("-- ms", size=10, color=C_DIM)

        tile = make_tile(
            cfg["label"],
            ft.Column(
                [
                    ft.Row([state_box, ft.Text("·", size=10,
                           color=C_DIM2), latency], spacing=6),
                    activate_btn,
                    hint,
                ],
                spacing=6,
            ),
            col=6,
        )
        door_tiles_row.controls.append(tile)
        door_refs[side] = {
            "state_box": state_box,
            "state_txt": state_txt,
            "activate_btn": activate_btn,
            "hint": hint,
            "latency": latency,
        }

    meta_row = ft.ResponsiveRow(spacing=6, run_spacing=6)
    outputs_row = ft.ResponsiveRow(spacing=6, run_spacing=6)

    sw_right_box, sw_right_txt = make_status_badge("MANUAL", "off")
    sw_left_box, sw_left_txt = make_status_badge("IDLE", "off")

    switch_tile = make_tile(
        "SWITCH STATUS",
        ft.Column(
            [
                ft.Row([ft.Text("RIGHT", size=10, color=C_DIM),
                       sw_right_box], spacing=8),
                ft.Row([ft.Text("LEFT", size=10, color=C_DIM),
                       sw_left_box], spacing=8),
            ],
            spacing=6,
        ),
        col=12,
        title_size=11,
        pad=11,
        border_color="#2c2c2c",
    )

    garage_section = make_tile(
        "GARAGE DOORS",
        door_tiles_row,
        col=12,
        title_size=11,
        pad=12,
        border_color="#2c2c2c",
    )
    plc_section = make_tile(
        "PLC",
        ft.Column([
            meta_row,
            switch_tile,
            outputs_row,
        ], spacing=8),
        col=12,
        title_size=11,
        pad=12,
        border_color="#2c2c2c",
    )

    content = ft.Column(
        [
            ft.Container(
                bgcolor=C_BG,
                border=ft.Border(bottom=ft.BorderSide(1, C_BORDER)),
                padding=ft.Padding(0, 0, 0, 10),
                content=ft.ResponsiveRow(
                    [
                        ft.Container(
                            col={"xs": 12, "md": 6},
                            content=ft.Column(
                                [
                                    ft.Text("Buzsak Auto Home", size=18,
                                            color=C_TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Row([header_fw, header_latency],
                                           spacing=10),
                                ],
                                spacing=2,
                            ),
                        ),
                        ft.Container(
                            col={"xs": 12, "md": 6},
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [header_dot, header_plc_ip], spacing=6),
                                    ft.Row(
                                        [header_matter_dot, header_matter_ip], spacing=6),
                                ],
                                spacing=2,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                            alignment=ft.alignment.center_right,
                        ),
                    ],
                    run_spacing=6,
                ),
            ),
            ft.Container(
                bgcolor=C_SURFACE,
                border=border_all(1, C_BORDER),
                border_radius=6,
                padding=10,
                content=ft.Column(
                    [
                        ft.Row([rc_label, arm_badge_box], spacing=10),
                        ft.Row([rc_slider], spacing=10),
                        err_text,
                    ],
                    spacing=8,
                ),
            ),
            garage_section,
            plc_section,
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    page.add(content)

    def _set_remote(active: bool):
        _remote_active[0] = active
        rc_slider.value = 100 if active else 0
        rc_slider.active_color = C_ON if active else "#2f3f33"
        set_status_badge(arm_badge_box, arm_badge_txt,
                         "on" if active else "off")
        arm_badge_txt.value = "ARMED" if active else "LOCKED"
        with _lock:
            _st["changed"] = True
        page.update()

    def _on_rc_change(_e):
        # Safety-first: moving away from full-right instantly disarms.
        if _remote_active[0] and (rc_slider.value or 0) < 100:
            _set_remote(False)

    def _on_rc_end(_e):
        # Only an exact full-right release arms; otherwise snap to left.
        _set_remote((rc_slider.value or 0) >= 100)

    rc_slider.on_change = _on_rc_change
    rc_slider.on_change_end = _on_rc_end
    _set_remote(False)

    def _matter_call(command: str, args: dict, timeout: float = MATTER_TIMEOUT):
        urls = [_matter_last_url[0]] + \
            [u for u in MATTER_WS_URLS if u != _matter_last_url[0]]
        errors: list[str] = []

        for url in urls:
            for attempt in range(1, MATTER_CONNECT_RETRIES + 1):
                t0 = time.monotonic()
                ws = None
                try:
                    ws = websocket.create_connection(url, timeout=timeout)
                    ws.settimeout(timeout)
                    ws.recv()
                    ws.send(json.dumps(
                        {"message_id": "1", "command": command, "args": args}))
                    while True:
                        data = json.loads(ws.recv())
                        if data.get("message_id") != "1":
                            continue
                        if data.get("error_code") is not None:
                            raise RuntimeError(data.get("details")
                                               or f"Matter error {data['error_code']}")
                        _matter_last_url[0] = url
                        ms = round((time.monotonic() - t0) * 1000)
                        return data.get("result"), ms
                except Exception as ex:
                    errors.append(
                        f"{url} try {attempt}/{MATTER_CONNECT_RETRIES}: {ex}")
                    if attempt < MATTER_CONNECT_RETRIES:
                        time.sleep(0.15 * attempt)
                finally:
                    if ws is not None:
                        ws.close()

        raise RuntimeError("Matter ws failed: " + " | ".join(errors[-4:]))

    def _matter_device_command(node_id: int, command_name: str):
        _matter_call(
            "device_command",
            {
                "node_id": node_id,
                "endpoint_id": MATTER_ENDPOINT_ID,
                "cluster_id": MATTER_ONOFF_CLUSTER,
                "command_name": command_name,
                "payload": {},
            },
        )

    def _matter_read_on_state(node_id: int):
        result, ms = _matter_call(
            "read_attribute",
            {
                "node_id": node_id,
                "attribute_path": f"{MATTER_ENDPOINT_ID}/{MATTER_ONOFF_CLUSTER}/0",
            },
        )
        key = f"{MATTER_ENDPOINT_ID}/{MATTER_ONOFF_CLUSTER}/0"
        return bool(result.get(key)), ms

    def _pulse_door(side: str):
        if not _remote_active[0]:
            return
        node_id = MATTER_DOORS[side]["node_id"]
        p = key_prefix(side)
        try:
            _matter_device_command(node_id, "Off")
            time.sleep(0.05)
            _matter_device_command(node_id, "On")
            time.sleep(MATTER_PULSE_SECONDS)
            _matter_device_command(node_id, "Off")
            with _lock:
                _st.update(**{f"{p}_ok": True, f"{p}_on": False,
                           f"{p}_err": "", "changed": True})
        except Exception as ex:
            with _lock:
                _st.update(
                    **{f"{p}_ok": False, f"{p}_err": str(ex), "changed": True})

    for side in MATTER_DOORS:
        door_refs[side]["activate_btn"].on_click = lambda _e, s=side: threading.Thread(
            target=_pulse_door, args=(s,), daemon=True
        ).start()

    def _render_meta_tiles(data: dict):
        def _pick_metric(source: dict, names: list[str]):
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

        def _pick_analog_metric(source: dict, metric_name: str, value_keys: list[str]):
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

        water_level = _pick_analog_metric(
            data, "water_level", ["liters", "value", "level"])
        if water_level == "--":
            water_level = _pick_metric(
                data,
                ["water_level", "waterLevel", "tank_level", "tankLevel", "level"],
            )

        pressure = _pick_analog_metric(
            data, "pressure", ["bar", "value", "pressure"])
        if pressure == "--":
            pressure = _pick_metric(
                data,
                ["pressure", "pressure_bar", "pressureBar", "plc_pressure"],
            )

        water_text = f"{water_level} L" if water_level != "--" else "--"
        pressure_text = f"{pressure} bar" if pressure != "--" else "--"

        meta_row.controls = [
            make_tile("Water Level", ft.Text(water_text, size=17, color=C_TEXT,
                      weight=ft.FontWeight.BOLD), col=6),
            make_tile("Pressure", ft.Text(pressure_text, size=17, color=C_TEXT,
                      weight=ft.FontWeight.BOLD), col=6),
        ]

    def _render_io_tiles(data: dict, blink_on: bool):
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

        # On this PLC image, the selector contact names are physically inverted.
        # Observed live state: switch in right position -> left_sw=True, right_sw=False.
        if raw_left_sw != raw_right_sw:
            right_auto = raw_left_sw
            left_well_pump = raw_right_sw
        else:
            right_auto = raw_right_sw
            left_well_pump = raw_left_sw

        sw_right_txt.value = "AUTO" if right_auto else "MANUAL"
        set_status_badge(sw_right_box, sw_right_txt,
                         "on" if right_auto else "off")

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

    def _refresh_door_controls(snap: dict):
        for side in MATTER_DOORS:
            p = key_prefix(side)
            ok = bool(snap.get(f"{p}_ok"))
            is_on = bool(snap.get(f"{p}_on"))
            ms = snap.get(f"{p}_ms", 0)
            ref = door_refs[side]

            ref["latency"].value = f"{ms} ms" if ok else "-- ms"
            can_trigger = _remote_active[0] and ok
            ref["activate_btn"].disabled = not can_trigger
            ref["activate_btn"].style = ft.ButtonStyle(
                bgcolor="#14532d" if can_trigger else "#2a2a2a",
                color="#eafff1" if can_trigger else "#8a8a8a",
                side=ft.BorderSide(1, "#1f8a4a" if can_trigger else C_BORDER),
                shape=ft.RoundedRectangleBorder(radius=4),
            )

            if not ok:
                ref["state_txt"].value = "OFFLINE"
                set_status_badge(ref["state_box"], ref["state_txt"], "warn")
                err_msg = str(snap.get(f"{p}_err", ""))
                if "not (yet) available" in err_msg:
                    ref["hint"].value = "Node unavailable"
                else:
                    ref["hint"].value = "Matter offline"
                ref["hint"].color = C_WARN
            elif is_on:
                ref["state_txt"].value = "ON"
                set_status_badge(ref["state_box"], ref["state_txt"], "amber")
                ref["hint"].value = "Pulse active"
                ref["hint"].color = C_DIM
            else:
                ref["state_txt"].value = "OFF"
                set_status_badge(ref["state_box"], ref["state_txt"], "on")
                if _remote_active[0]:
                    ref["hint"].value = "Ready · 0.5s pulse"
                    ref["hint"].color = C_DIM
                else:
                    ref["hint"].value = "Slide REMOTE ARM to enable"
                    ref["hint"].color = C_DIM

    def fetch_direct():
        while True:
            try:
                t0 = time.monotonic()
                data = requests.get(
                    PLC_DIRECT_URL, timeout=TIMEOUT_DIRECT).json()
                ms = round((time.monotonic() - t0) * 1000)
                with _lock:
                    _st.update(d_ok=True, d_ms=ms, d_data=data,
                               d_err="", changed=True)
            except Exception as ex:
                with _lock:
                    _st.update(d_ok=False, d_data=None,
                               d_err=str(ex), changed=True)
            time.sleep(POLL_DIRECT)

    def fetch_matter():
        fail_streak = {key_prefix(side): 0 for side in MATTER_DOORS}
        while True:
            updates = {"changed": True}
            with _lock:
                prev = {}
                for side in MATTER_DOORS:
                    p = key_prefix(side)
                    prev[f"{p}_ok"] = bool(_st.get(f"{p}_ok"))
                    prev[f"{p}_on"] = bool(_st.get(f"{p}_on"))
                    prev[f"{p}_ms"] = int(_st.get(f"{p}_ms", 0))
            for side, cfg in MATTER_DOORS.items():
                p = key_prefix(side)
                try:
                    is_on, ms = _matter_read_on_state(cfg["node_id"])
                    fail_streak[p] = 0
                    updates[f"{p}_ok"] = True
                    updates[f"{p}_ms"] = ms
                    updates[f"{p}_on"] = is_on
                    updates[f"{p}_err"] = ""
                except Exception as ex:
                    fail_streak[p] += 1
                    if fail_streak[p] >= MATTER_FAILS_TO_OFFLINE:
                        updates[f"{p}_ok"] = False
                        updates[f"{p}_err"] = str(ex)
                    else:
                        # Keep last known state during brief Matter restarts/reboots.
                        updates[f"{p}_ok"] = prev.get(f"{p}_ok", False)
                        updates[f"{p}_on"] = prev.get(f"{p}_on", False)
                        updates[f"{p}_ms"] = prev.get(f"{p}_ms", 0)
                        updates[f"{p}_err"] = ""
            with _lock:
                _st.update(**updates)
            time.sleep(POLL_MATTER)

    def enforce_off_default_once():
        updates = {"changed": True}
        for side, cfg in MATTER_DOORS.items():
            p = key_prefix(side)
            try:
                _matter_device_command(cfg["node_id"], "Off")
                updates[f"{p}_on"] = False
            except Exception:
                continue
        with _lock:
            _st.update(**updates)

    async def ui_loop():
        while True:
            await asyncio.sleep(UI_TICK)
            with _lock:
                if not _st["changed"]:
                    continue
                snap = dict(_st)
                _st["changed"] = False

            data = snap["d_data"]
            matter_ok = bool(snap.get("mr_ok") or snap.get("ml_ok"))
            header_matter_dot.bgcolor = C_ON if matter_ok else C_WARN
            header_matter_ip.value = f"Matter: {_matter_last_url[0].replace('ws://', '').replace('/ws', '')}"
            header_latency.value = f"{snap['d_ms']} ms" if snap["d_ok"] else "-- ms"

            if snap["d_ok"] and data:
                header_dot.bgcolor = C_ON
                header_plc_ip.value = f"PLC: {data.get('ip', '--')}"
                fw = str(data.get("firmware", ""))
                header_fw.value = f"v{fw.replace('v', '')}" if fw else ""
                _render_meta_tiles(data)
                _render_io_tiles(data, int(time.time()) % 2 == 0)
            else:
                header_dot.bgcolor = C_WARN
                header_plc_ip.value = "PLC: disconnected"
                header_fw.value = ""

            _refresh_door_controls(snap)

            err = ""
            if not snap["d_ok"]:
                err = snap["d_err"]

            if not err:
                for side in MATTER_DOORS:
                    p = key_prefix(side)
                    if snap.get(f"{p}_err"):
                        err = snap[f"{p}_err"]
                        break

            err_text.visible = bool(err)
            err_text.value = err
            page.update()

    threading.Thread(target=fetch_direct, daemon=True).start()
    threading.Thread(target=fetch_matter, daemon=True).start()
    threading.Thread(target=enforce_off_default_once, daemon=True).start()
    page.run_task(ui_loop)


ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=8550)
