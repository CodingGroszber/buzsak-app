"""Dashboard page composition and runtime orchestration."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Any

import flet as ft
import requests

from app.constants import (
    C_BG,
    C_BORDER,
    C_DIM,
    C_DIM2,
    C_ON,
    C_SURFACE,
    C_TEXT,
    C_WARN,
    MATTER_CONNECT_RETRIES,
    MATTER_DOORS,
    MATTER_ENDPOINT_ID,
    MATTER_FAILS_TO_OFFLINE,
    MATTER_ONOFF_CLUSTER,
    MATTER_PULSE_SECONDS,
    MATTER_TIMEOUT,
    MATTER_WS_URLS,
    PLC_DIRECT_URL,
    POLL_DIRECT,
    POLL_MATTER,
    TIMEOUT_DIRECT,
    UI_TICK,
    key_prefix,
)
from app.matter import MatterClient, MatterClientError
from app.plc_view import render_io_tiles, render_meta_tiles
from app.safety import DotUnlockControl
from app.ui_helpers import border_all, io_tile, make_status_badge, make_tile, set_status_badge


@dataclass
class DoorUIRefs:
    """Strongly typed references to one garage tile's mutable controls."""

    state_box: ft.Container
    state_txt: ft.Text
    activate_btn: ft.FilledButton
    hint: ft.Text
    latency: ft.Text


def build_page(page: ft.Page) -> None:
    """Build and run the dashboard page and background polling loops."""
    page.title = "Buzsak Auto Home"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = C_BG
    page.padding = 12

    state: dict[str, Any] = {
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
    state_lock = threading.Lock()

    matter_client = MatterClient(
        urls=MATTER_WS_URLS,
        connect_retries=MATTER_CONNECT_RETRIES,
        timeout=MATTER_TIMEOUT,
        endpoint_id=MATTER_ENDPOINT_ID,
        onoff_cluster=MATTER_ONOFF_CLUSTER,
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
    arm_badge_box, arm_badge_txt = make_status_badge("LOCKED", "off")

    def _on_arm_change(armed: bool) -> None:
        set_status_badge(arm_badge_box, arm_badge_txt,
                         "on" if armed else "off")
        arm_badge_txt.value = "ARMED" if armed else "LOCKED"
        with state_lock:
            state["changed"] = True

    dot_unlock = DotUnlockControl(on_arm=_on_arm_change, page=page)

    door_refs: dict[str, DoorUIRefs] = {}
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
        hint = ft.Text("Connect dots to enable", size=10, color=C_DIM)
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
        door_refs[side] = DoorUIRefs(
            state_box=state_box,
            state_txt=state_txt,
            activate_btn=activate_btn,
            hint=hint,
            latency=latency,
        )

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
        ft.Column([meta_row, switch_tile, outputs_row], spacing=8),
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
                                    ft.Text(
                                        "Buzsak Auto Home",
                                        size=18,
                                        color=C_TEXT,
                                        weight=ft.FontWeight.BOLD,
                                    ),
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
                            alignment=ft.alignment.Alignment(1, 0),
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
                        ft.Row([dot_unlock.control], spacing=10),
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

    def mark_changed() -> None:
        """Flag state updates for the UI task."""
        with state_lock:
            state["changed"] = True

    def pulse_door(side: str) -> None:
        """Trigger a door pulse when safety arm allows it."""
        if not dot_unlock.active:
            return
        node_id = MATTER_DOORS[side]["node_id"]
        prefix = key_prefix(side)
        try:
            matter_client.pulse_door(node_id, MATTER_PULSE_SECONDS)
            with state_lock:
                state.update(
                    **{
                        f"{prefix}_ok": True,
                        f"{prefix}_on": False,
                        f"{prefix}_err": "",
                        "changed": True,
                    }
                )
        except MatterClientError as ex:
            with state_lock:
                state.update(**{f"{prefix}_ok": False,
                             f"{prefix}_err": str(ex), "changed": True})

    for side in MATTER_DOORS:
        door_refs[side].activate_btn.on_click = lambda _e, s=side: threading.Thread(
            target=pulse_door,
            args=(s,),
            daemon=True,
        ).start()

    def refresh_door_controls(snapshot: dict[str, Any]) -> None:
        """Apply Matter state to door tiles and trigger button states."""
        for side in MATTER_DOORS:
            prefix = key_prefix(side)
            ok = bool(snapshot.get(f"{prefix}_ok"))
            is_on = bool(snapshot.get(f"{prefix}_on"))
            latency_ms = snapshot.get(f"{prefix}_ms", 0)
            ref = door_refs[side]

            ref.latency.value = f"{latency_ms} ms" if ok else "-- ms"
            can_trigger = dot_unlock.active and ok
            ref.activate_btn.disabled = not can_trigger
            ref.activate_btn.style = ft.ButtonStyle(
                bgcolor="#14532d" if can_trigger else "#2a2a2a",
                color="#eafff1" if can_trigger else "#8a8a8a",
                side=ft.BorderSide(1, "#1f8a4a" if can_trigger else C_BORDER),
                shape=ft.RoundedRectangleBorder(radius=4),
            )

            if not ok:
                ref.state_txt.value = "OFFLINE"
                set_status_badge(ref.state_box, ref.state_txt, "warn")
                err_msg = str(snapshot.get(f"{prefix}_err", ""))
                ref.hint.value = "Node unavailable" if "not (yet) available" in err_msg else "Matter offline"
                ref.hint.color = C_WARN
            elif is_on:
                ref.state_txt.value = "ON"
                set_status_badge(ref.state_box, ref.state_txt, "amber")
                ref.hint.value = "Pulse active"
                ref.hint.color = C_DIM
            else:
                ref.state_txt.value = "OFF"
                set_status_badge(ref.state_box, ref.state_txt, "on")
                if dot_unlock.active:
                    ref.hint.value = "Ready · 0.5s pulse"
                    ref.hint.color = C_DIM
                else:
                    ref.hint.value = "Connect dots to enable"
                    ref.hint.color = C_DIM

    def fetch_direct() -> None:
        """Poll PLC HTTP endpoint and cache latest payload."""
        while True:
            try:
                t0 = time.monotonic()
                data = requests.get(
                    PLC_DIRECT_URL, timeout=TIMEOUT_DIRECT).json()
                latency_ms = round((time.monotonic() - t0) * 1000)
                with state_lock:
                    state.update(d_ok=True, d_ms=latency_ms,
                                 d_data=data, d_err="", changed=True)
            except (requests.RequestException, ValueError) as ex:
                with state_lock:
                    state.update(d_ok=False, d_data=None,
                                 d_err=str(ex), changed=True)
            time.sleep(POLL_DIRECT)

    def fetch_matter() -> None:
        """Poll Matter door states with transient-failure tolerance."""
        fail_streak = {key_prefix(side): 0 for side in MATTER_DOORS}
        while True:
            updates: dict[str, Any] = {"changed": True}
            with state_lock:
                previous: dict[str, Any] = {}
                for side in MATTER_DOORS:
                    prefix = key_prefix(side)
                    previous[f"{prefix}_ok"] = bool(state.get(f"{prefix}_ok"))
                    previous[f"{prefix}_on"] = bool(state.get(f"{prefix}_on"))
                    previous[f"{prefix}_ms"] = int(
                        state.get(f"{prefix}_ms", 0))

            for side, cfg in MATTER_DOORS.items():
                prefix = key_prefix(side)
                try:
                    is_on, latency_ms = matter_client.read_on_state(
                        cfg["node_id"])
                    fail_streak[prefix] = 0
                    updates[f"{prefix}_ok"] = True
                    updates[f"{prefix}_ms"] = latency_ms
                    updates[f"{prefix}_on"] = is_on
                    updates[f"{prefix}_err"] = ""
                except MatterClientError as ex:
                    fail_streak[prefix] += 1
                    if fail_streak[prefix] >= MATTER_FAILS_TO_OFFLINE:
                        updates[f"{prefix}_ok"] = False
                        updates[f"{prefix}_err"] = str(ex)
                    else:
                        # Keep last known state during brief Matter restarts/reboots.
                        updates[f"{prefix}_ok"] = previous.get(
                            f"{prefix}_ok", False)
                        updates[f"{prefix}_on"] = previous.get(
                            f"{prefix}_on", False)
                        updates[f"{prefix}_ms"] = previous.get(
                            f"{prefix}_ms", 0)
                        updates[f"{prefix}_err"] = ""

            with state_lock:
                state.update(**updates)
            time.sleep(POLL_MATTER)

    def enforce_off_default_once() -> None:
        """Best-effort startup guard to leave door relays in Off state."""
        updates: dict[str, Any] = {"changed": True}
        node_result = matter_client.enforce_off_defaults(
            [cfg["node_id"] for cfg in MATTER_DOORS.values()])
        for side, cfg in MATTER_DOORS.items():
            if node_result.get(cfg["node_id"]):
                prefix = key_prefix(side)
                updates[f"{prefix}_on"] = False
        with state_lock:
            state.update(**updates)

    async def ui_loop() -> None:
        """Render periodic updates onto page controls when state changes."""
        while True:
            await asyncio.sleep(UI_TICK)
            with state_lock:
                if not state["changed"]:
                    continue
                snapshot = dict(state)
                state["changed"] = False

            data = snapshot["d_data"]
            matter_ok = bool(snapshot.get("mr_ok") or snapshot.get("ml_ok"))
            header_matter_dot.bgcolor = C_ON if matter_ok else C_WARN
            header_matter_ip.value = (
                f"Matter: {matter_client.last_url.replace('ws://', '').replace('/ws', '')}"
            )
            header_latency.value = f"{snapshot['d_ms']} ms" if snapshot["d_ok"] else "-- ms"

            if snapshot["d_ok"] and data:
                header_dot.bgcolor = C_ON
                header_plc_ip.value = f"PLC: {data.get('ip', '--')}"
                firmware = str(data.get("firmware", ""))
                header_fw.value = f"v{firmware.replace('v', '')}" if firmware else ""
                render_meta_tiles(data, make_tile, meta_row)
                render_io_tiles(
                    data,
                    int(time.time()) % 2 == 0,
                    outputs_row,
                    io_tile,
                    sw_right_box,
                    sw_right_txt,
                    sw_left_box,
                    sw_left_txt,
                    set_status_badge,
                )
            else:
                header_dot.bgcolor = C_WARN
                header_plc_ip.value = "PLC: disconnected"
                header_fw.value = ""

            refresh_door_controls(snapshot)

            error_message = ""
            if not snapshot["d_ok"]:
                error_message = snapshot["d_err"]

            if not error_message:
                for side in MATTER_DOORS:
                    prefix = key_prefix(side)
                    if snapshot.get(f"{prefix}_err"):
                        error_message = snapshot[f"{prefix}_err"]
                        break

            err_text.visible = bool(error_message)
            err_text.value = error_message
            page.update()

    threading.Thread(target=fetch_direct, daemon=True).start()
    threading.Thread(target=fetch_matter, daemon=True).start()
    threading.Thread(target=enforce_off_default_once, daemon=True).start()
    page.run_task(ui_loop)
