# Buzsák App — Requirements Specification

| Field | Value |
|---|---|
| Document | `requirements.md` (authoritative specification of the Android client) |
| Product | **Buzsák App**, an Android client for the Buzsák garden telemetry and command server |
| Reference system | `C:\Scripts\Python\buzsak_pi3_server` (the "server") |
| Status | Draft v0.1. Implementation has not started |
| Date | 2026-10-05 |
| Owner | Project owner (single maintainer) |

Each requirement has an ID such as `ARC-03`. Use these IDs in code docstrings, commits, tests and documentation. When this document conflicts with any other file in this repository, this document wins. When it conflicts with the server's `requirements.md` on a server-side matter, the server's specification wins and this document must be updated.

The words **MUST**, **MUST NOT**, **SHOULD** and **MAY** follow RFC 2119.

---

## 1. Purpose and context

### 1.1 What the server does (verified against the reference project)

The server is a self-hosted, LAN-only garden telemetry and command system running on a **Raspberry Pi 3** (`rpi3`, `192.168.1.95`, user `neulas`). It runs as three systemd services:

| Process | Role |
|---|---|
| `buzsak-poller` | Polls every enabled LAN device, by default every 1 s. It normalizes payloads into parameters, writes them to SQLite, and tracks device health (`healthy` / `degraded` / `offline`) |
| `buzsak-dispatcher` | Executes queued commands. Today it handles only the Sonoff pulse |
| `buzsak-web` | Runs Flask under gunicorn on `0.0.0.0:8080`. It serves the browser dashboard and a JSON API |

It manages these sub-devices:

| Party / tab | Device id | Kind | Hardware and protocol |
|---|---|---|---|
| PUMP (garden PLC) | `garden-plc` | `garden_plc` | ESP32 PLC, HTTP JSON, `192.168.1.94` |
| GREENHOUSE (valve control) | `valve-controller` | `valve_controller` | ESP32 with four relays and two RS485 temperature/humidity probes, HTTP JSON, `192.168.1.109` |
| GARAGE | `sonoff-1` (right), `sonoff-2` (left) | `sonoff_minid` | Sonoff MINI-D through python-matter-server (WebSocket `:5580`) |

The SQLite database (WAL mode) is the system of record. It holds:
- the device registry (`devices`);
- the KPI catalog (`parameters`) and control-signal catalog (`capabilities`);
- the latest values (`observations_latest`) and append-only history (`observations_history`);
- device health (`device_health`);
- the command queue (`pulse_requests`; a general command table is planned).

Values carry a **quality** (`good`, `stale`, `unavailable`, `invalid`). The server keeps false, zero, null, invalid, unavailable and stale as distinct states.

**Constraint inherited from the server (server ARC-05):** the SQLite file MUST NOT be exposed or accessed directly by clients. All client access goes through the server's HTTP API.

### 1.2 What this app is

The Buzsák App is an **Android-only** mobile client. It:
- shows every KPI the server holds, live;
- shows the state of every control signal;
- lets the operator issue ValveControl commands and server-controlled pulses for both Garage doors.

The app is a *view and command terminal*. It holds no authoritative state of its own.

### 1.3 Glossary

| Term | Meaning |
|---|---|
| KPI / parameter | An observed value from the server's `parameters` catalog, e.g. `pressure_bar` or `sensor_a_humidity_pct` |
| Control signal / capability | A command the server can execute, from the `capabilities` catalog, e.g. `set_output` or `set_mode` |
| Party | A group of devices shown as one tab: PUMP, GREENHOUSE or GARAGE |
| Snapshot | One response from the server's state endpoint |
| SSOT | Single source of truth: the server database, reached through the server API |
| Acknowledged | The server or device accepted a command |
| Confirmed | Fresh telemetry from the server shows the requested state |

---

## 2. Scope

### 2.1 In scope (release 1.0)

- Android app (phone first; tablet layout SHOULD work).
- Live, automatically refreshing read-only view of **all** server KPIs, device health and capabilities.
- ValveControl commands: `set_mode` (manual/automatic) and `set_output` for relay1–relay4.
- One server-controlled pulse for each Garage device (`sonoff-1`, `sonoff-2`).
- Tabbed UI with one tab per party, plus an Overview tab and a System tab.
- Python single-stack implementation (see ARC).
- Build, run and deploy on the developer machine (Windows 11 with Android Studio tooling) and on physical Android devices.
- Complete developer documentation.

### 2.2 Out of scope (release 1.0)

- iOS, web or desktop *distribution*. Desktop runs are allowed for development only.
- Control of the PLC pumps (`garden_plc.set_output`). They remain read-only, with the reason they are disabled.
- Calls from the app directly to the devices (ESP32 / Matter). These are **forbidden** (see SSOT-03).
- A local authoritative database, offline command queueing, or offline replay.
- Google Play publication. Distribution is by sideloaded APK.
- RS485 commissioning (`/api/rs485*`) and device OTA (`/update`) functions.

### 2.3 Later (backlog candidates, not yet approved)

- PLC pump control, once its server-side command path is approved.
- Remote access over Tailscale.
- Push notifications, e.g. for a device going offline or low water.
- Home-screen widget.

---

## 3. Single source of truth (SSOT)

| ID | Requirement |
|---|---|
| SSOT-01 | The server database MUST be the only source of truth for every KPI value, quality, device health, capability and command status shown in the app. |
| SSOT-02 | The app MUST read that data **only through the server HTTP API**. It MUST NOT open, copy, mount or sync the SQLite file (server ARC-05). |
| SSOT-03 | The app MUST NOT talk directly to field devices (ESP32 PLC, valve controller, Matter server). Every command goes through the server. |
| SSOT-04 | The app MUST NOT compute or invent physical state. It displays what the server reports. The only exceptions are presentation conversions such as formatting and local relative time ("3 s ago"). |
| SSOT-05 | The app MAY keep the **last received snapshot** in memory, and MAY keep it on disk, so it can render instantly at startup. Any cached data MUST be visibly marked as cached/stale until a fresh snapshot arrives. |
| SSOT-06 | The app MUST NOT optimistically show a control as changed. A control shows its new state only after the server reports it (see CTL-05). |
| SSOT-07 | The catalog of parameters, capabilities and devices MUST be driven by the server response, not hard-coded. A new parameter on the server MUST appear in the app without an app release, using a generic fallback rendering. Hard-coded *presentation metadata* (labels, icons, ordering, formatting) is allowed, keyed by `parameter_id`. |
| SSOT-08 | Whether a capability is enabled MUST come from the server (`capabilities[].enabled` and `disabled_reason`). The app MAY add stricter client-side guards (see VLV), but it MUST NOT enable a control the server reports as disabled. |

---

## 4. Data: KPIs and control signals

### 4.1 Value semantics

| ID | Requirement |
|---|---|
| DATA-01 | Server values arrive as strings plus a `value_type` (`bool`, `int`, `float`, `string`, `null`). The app MUST parse them into typed values in a single, unit-tested domain module. |
| DATA-02 | The app MUST visually distinguish these states: **good**, **stale** (`stale == true`), **unavailable**, **invalid**, **no data yet** (`has_data == false`), and the legitimate values `false` / `0`. A missing value MUST NOT be rendered as `0` or `off`. |
| DATA-03 | Every KPI MUST show its unit when it has one (`bar`, `L`, `°C`, `%`, `ratio`, `s`). A `ratio` SHOULD be displayed as a percentage. |
| DATA-04 | Every KPI MUST let the user see `observed_at` and `last_changed_at`, for example on tap or long-press. |
| DATA-05 | Device health (`status`, `last_success_at`, `last_error`, `consecutive_failures`) MUST be visible per device. |
| DATA-06 | Timestamps from the server are UTC. The app MUST display them in the device's local time zone (Europe/Budapest expected). |

### 4.2 KPI catalog (current server catalog, informative)

**PUMP — `garden_plc` (`garden-plc`)**

| parameter_id | Category | Unit | Notes |
|---|---|---|---|
| `well_pump` | boolean | – | Pump relay (read-only in the app for 1.0) |
| `tank_pump` | boolean | – | Pump relay (read-only in the app for 1.0) |
| `right_sw`, `left_sw` | boolean | – | Digital inputs |
| `switch_led`, `wifi_led` | boolean | – | LED outputs |
| `pressure_bar` | continuous | bar | Below about 0.1 bar the value is `invalid`/null |
| `water_level_liters` | continuous | L | 0–1000. The sensor is known to over-range, so the UI SHOULD carry a reliability note |

**GREENHOUSE — `valve_controller` (`valve-controller`)**

| parameter_id | Category | Unit | Notes |
|---|---|---|---|
| `relay1_mist` | boolean | – | Mist valve; also the humidity-automation valve |
| `relay2_rain` | boolean | – | Rain valve |
| `relay3_drip` | boolean | – | Drip valve |
| `relay4_light` | boolean | – | Light |
| `mode` | configuration | – | `manual` / `automatic` |
| `sensor_a_temperature_c`, `sensor_b_temperature_c` | continuous | °C | |
| `sensor_a_humidity_pct`, `sensor_b_humidity_pct` | continuous | % | 0–100 |
| `automation_valve_on` | boolean | – | |
| `automation_target_pct` | continuous | % | Currently 90 |
| `automation_duty` | continuous | ratio | 0–1 |
| `automation_period_s` | configuration | s | Currently 600 |
| `automation_elapsed_s` | continuous | s | 0 to the period |
| `automation_sensor_valid`, `automation_time_synced` | boolean | – | |

All `automation_*` values are frozen while `mode == manual`. The UI MUST then show them as *inactive / frozen*, even though their quality is `good`.

**GARAGE — `sonoff_minid` (`sonoff-1` GARAGE-RIGHT, `sonoff-2` GARAGE-LEFT)**

| parameter_id | Category | Notes |
|---|---|---|
| `on_off` | boolean | Matter OnOff |

### 4.3 Control-signal catalog (current server catalog, informative)

| Device kind | action_id | params_schema | Server status | App 1.0 |
|---|---|---|---|---|
| `valve_controller` | `set_output` | `{"name": ["relay1".."relay4"], "state": "bool"}` | Registered, **not implemented** | **Implement** (enabled when the server enables it) |
| `valve_controller` | `set_mode` | `{"value": ["manual","automatic"]}` | Registered, **not implemented** | **Implement** (enabled when the server enables it) |
| `garden_plc` | `set_output` | `{"name": ["well_pump","tank_pump"], "state": "bool"}` | Registered, not implemented | Read-only display |
| `sonoff_minid` | `pulse` | `{}` | **Implemented** | Trigger buttons for Garage Right (`sonoff-1`) and Garage Left (`sonoff-2`) |

---

## 5. Server API dependencies (SRV)

The app depends on server endpoints, some of which do not exist yet. These are **requests to the server project**. The final contract is owned and specified in `buzsak_pi3_server/requirements.md`, and this table MUST be kept in sync with it. The detailed request for the server developer is [change_proposal.md](change_proposal.md).

| ID | Dependency | Server status | App behavior until available |
|---|---|---|---|
| SRV-01 | `GET /api/dashboard/state`: full snapshot (parties → devices → health, parameters, capabilities, last_pulse) | **Available** | Primary data source for 1.0 |
| SRV-02 | `GET /healthz`, `GET /readyz` | **Available** | Used for the connection check and the System tab |
| SRV-03 | Versioned API `GET /api/v1/state` (server API-01) | Planned | Use SRV-01. The endpoint path MUST be configurable in one place |
| SRV-04 | Valve command submission, e.g. `POST /api/v1/devices/{device_id}/commands` with `{action_id, params, idempotency_key, client_origin}` returning `202 {command_id, status, status_url, expires_at}` (server CMD lifecycle §9, API-09) | **Implemented in server code** (2026-10-07), enabled only when the server's `control.valve_enabled` is true | Valve controls stay **disabled** while the server reports `enabled: false`, showing its `disabled_reason` |
| SRV-05 | Command status `GET /api/v1/commands/{command_id}` with lifecycle `pending → dispatching → sent → acknowledged → confirmed`, or `failed` / `expired` / `cancelled` / `uncertain` | **Implemented in server code** (2026-10-07) | As SRV-04 |
| SRV-06 | History endpoint for time series, e.g. `GET /api/v1/history?device_id=&parameter_id=&from=&to=` (server API-02) | Not implemented | Charts hidden. A sparkline MAY be built from in-memory samples collected during the session, labeled "this session only" |
| SRV-07 | Authentication (bearer token, viewer/operator/admin roles) and HTTPS (server SEC-02/04/05/06) | **Available (2026-10-07):** `https://192.168.1.95`, bearer tokens, `401` without one | The app sends the token and trusts only the pinned CA (ADR-0003) |
| SRV-08 | Push channel (Server-Sent Events or WebSocket) for state changes | Not planned | Polling (see UPD) |
| SRV-13 | Valve controller data parity: rain automation, per-relay `controllable` / `always_manual`, sensor error details, firmware (proposal CP-02..CP-04) | Implemented in server catalog; **live values verified 2026-10-07** through authenticated state GET | Greenhouse renders dedicated mist/rain schedules, sensor diagnostics and identity; missing fields remain explicit |
| SRV-14 | Valve command execution and capability enablement (proposal CP-05..CP-08, CP-12), extending SRV-04/05 | Implemented in server code; **relay4 LIGHT capability and confirmed on/off round trip verified live 2026-10-07** | Other relay/mode commands remain untested; Android UI verification pending |

| ID | Requirement |
|---|---|
| SRV-10 | All server access MUST go through one API client module. No other module may make HTTP calls. |
| SRV-11 | The API client MUST tolerate unknown extra fields and MUST reject or flag missing required fields without crashing the UI. |
| SRV-12 | The app MUST keep working read-only against any server that provides only SRV-01 and SRV-02. |

---

## 6. Architecture (ARC)

| ID | Requirement |
|---|---|
| ARC-01 | **Single-stack Python.** All application code (UI, state, networking, domain) MUST be Python ≥ 3.11 and < 3.13 (Flet's Android bundle supports 3.12–3.14 only; the cap keeps dev and APK on 3.12, ADR-0001). Native Kotlin/Java code is allowed only if a needed platform feature is impossible otherwise, and then only with an ADR (see DOC-04). |
| ARC-02 | **UI framework: [Flet](https://flet.dev)** (Python on Flutter). Its Material 3 widgets and native Android packaging (`flet build apk`/`aab`) fit the "modern yet clean" goal and work from Windows 11. Alternatives considered: BeeWare/Toga with Briefcase (weaker styling), and Kivy/KivyMD with Buildozer (no native Windows Android build). Record the decision in `docs/adr/0001-ui-framework.md`. Pin the exact Flet version in `pyproject.toml` / `uv.lock`, and verify it against the current Flet documentation at implementation time. |
| ARC-03 | **Package management:** `uv`, keeping the existing `pyproject.toml` and `uv_build` backend where compatible with Flet build. Flet-specific settings go under `[tool.flet]`. `flet build` ignores `uv.lock`, so runtime dependencies MUST be pinned with `==` in `[project].dependencies`; build tooling (`flet-cli`, `flet-desktop`) lives in the dev dependency group. |
| ARC-04 | **Layering**, with dependencies pointing downward only: <br>`ui/` (Flet views, components, UI Runtime and theme) → `state/` (snapshot store/diff, polling service, settings and secure-token repositories) → `domain/` (typed models, value parsing, quality semantics, presentation metadata) → `api/` (HTTP client, response validation and errors) <br>`domain/` and `api/` MUST NOT import Flet. The UI Runtime coordinates user command lifecycles; the state layer owns snapshot and polling state. |
| ARC-05 | `domain/` and `state/` MUST be pure Python, testable without a UI or a device. |
| ARC-06 | **One-way data flow:** the polling service fetches a snapshot, the store replaces state immutably, and views re-render from state. Views never mutate snapshot state directly; they dispatch user intents through the UI Runtime, which uses the API client and waits for server-reported status. |
| ARC-07 | Domain models SHOULD be frozen dataclasses. Use `from __future__ import annotations` (the same convention as the server). |
| ARC-08 | Networking MUST NOT block the UI thread. Use asyncio (`httpx.AsyncClient` or an equivalent pure-Python client compatible with Flet on Android). |
| ARC-09 | Configuration (server base URL, poll interval, timeouts, optional token) MUST live in one settings module. It is persisted with Flet client storage (never the token) and editable on the System tab. Defaults: `https://192.168.1.95`, poll every 2 s. |
| ARC-10 | Avoid speculative abstractions (YAGNI). Add no plugin systems or DI frameworks. |

Proposed layout (to be confirmed at implementation start):

```
buzsak_app/
├── pyproject.toml             # uv + [tool.flet] build config
├── requirements.md            # this file
├── README.md                  # quick start
├── CHANGELOG.md
├── .github/copilot-instructions.md
├── docs/
│   ├── architecture.md
│   ├── api-contract.md        # snapshot schema as consumed + SRV status
│   ├── ui-style-guide.md
│   ├── build-and-deploy.md
│   ├── testing.md
│   ├── tabs/{overview,pump,greenhouse,garage,system}.md
│   └── adr/NNNN-*.md
├── scripts/                   # PowerShell helpers (dev, build, install, logs)
├── src/
│   ├── main.py                # Flet entry point (ft.app / ft.run)
│   └── buzsak_app/
│       ├── api/  domain/  state/  ui/  settings.py
│       └── assets/            # icon, splash, fonts
└── tests/                     # pytest, fake server fixtures
```

---

## 7. Live update and smooth control (UPD)

| ID | Requirement |
|---|---|
| UPD-01 | While the app is in the foreground, it MUST refresh the snapshot automatically. The default interval is **2 s**, configurable from 1 to 30 s. The user never has to refresh manually. |
| UPD-02 | Pull-to-refresh or a refresh button MAY trigger an immediate fetch. |
| UPD-03 | Polling MUST pause when the app is backgrounded or the screen is off, and MUST resume immediately when the app returns to the foreground. |
| UPD-04 | Requests MUST NOT overlap. If a fetch is still running, the next tick is skipped. |
| UPD-05 | On errors, the app MUST back off exponentially (capped at 30 s) and MUST show a non-blocking connection banner (connecting / offline / server unhealthy). The last data stays visible and is marked stale. |
| UPD-06 | A global "last updated N s ago" indicator MUST always be visible. It turns into a warning when older than 3× the poll interval. |
| UPD-07 | **Smooth rendering:** only widgets whose data changed are updated, using parameter `revision` and `observed_at`. There must be no full-screen flicker, no layout jumps, and no reset of scroll position or the current tab. Value changes SHOULD animate subtly (≤ 250 ms). |
| UPD-08 | While a command is in flight, polling MUST temporarily tighten to 1 s for that device until the command reaches a final state or times out. |
| UPD-09 | **App self-update (SHOULD, phase 2):** the app checks a version manifest (for example served by the server or a release location set in settings), notifies when a newer APK exists, and opens the download or installer. Silent installs are not possible for sideloaded apps, and the app MUST NOT attempt them. |

---

## 8. Control: general command handling (CTL)

| ID | Requirement |
|---|---|
| CTL-01 | Every command sent through the versioned command API MUST include a client-generated **idempotency key** (UUID4). A manual retry reuses the same key only for the exact same intent. The non-idempotent Garage pulse is governed by CTL-11 and MUST NOT be retried. |
| CTL-02 | A control is interactive only if all of these hold: the server capability is `enabled`; device health is `healthy`; the relevant parameters are fresh (not stale, quality `good`); and no command is already in flight for the same target. Otherwise the control is disabled, and the reason is shown in plain language. |
| CTL-03 | Each command MUST show its lifecycle state inline in the Greenhouse control panel: *sending → pending → acknowledged → confirmed*, or *failed / expired / uncertain*, with a state-specific emoji, semantic color and safe reason where available. |
| CTL-04 | The app MUST NOT retry automatically. A lost submit response offers an explicit same-key retry; an accepted command with unknown outcome offers **Check status** (GET only). Re-dispatching a terminal failed/uncertain command requires a server contract that preserves idempotency and is tracked by B-211. |
| CTL-05 | **Confirmation** means the server reports the command as `confirmed`, or a server snapshot with `observed_at` later than the command submission time shows the requested value. HTTP 2xx alone counts only as *accepted*. |
| CTL-06 | If a command is not confirmed within a timeout (default 10 s, configurable), the app MUST show it as **uncertain**, retain its command ID, and offer a status-only check. It MUST NOT claim success or failure, and it keeps displaying the server's reported value. |
| CTL-07 | Controls MUST give immediate tactile and visual feedback (pressed state, haptic tick, progress indicator) within 100 ms, without changing the displayed physical state (SSOT-06). |
| CTL-08 | Double taps and rapid toggles MUST be debounced: one in-flight command per target. |
| CTL-09 | The app MUST log every command intent and outcome in an in-app session log, viewable on the System tab. The authoritative audit trail lives on the server. |
| CTL-10 | The UI MUST NOT imply physical effects it cannot verify. For example, a confirmed valve relay means "relay energized", not "water flowing" (server CMD-19). |
| CTL-11 | Garage pulses are non-idempotent momentary actions. For either Sonoff, the app MUST submit once and MUST NOT automatically or manually resubmit after an ambiguous outcome. HTTP 202 means accepted only; completion is reported only from a later server `last_pulse` snapshot. An explicit status check is GET-only. Each button MUST be enabled only when that device's pulse capability is enabled, health is healthy, and `on_off` is fresh and good. The UI MUST describe relay/pulse state, never infer door position. |

---

## 9. ValveControl (VLV), release-1.0 control scope

| ID | Requirement |
|---|---|
| VLV-01 | The GREENHOUSE tab MUST show a **mode** control (Manual / Automatic) and four relay switches: **Mist** (relay1), **Rain** (relay2), **Drip** (relay3) and **Light** (relay4). |
| VLV-02 | Relay switches MUST be enabled only when the latest fresh `mode` value is `manual`, in addition to CTL-02, **except** an output reported with fresh `always_manual == true` (the verified LIGHT/relay4 firmware exception). `controllable` MUST also be fresh and true. The device rejects other relay commands in automatic mode (HTTP 409). |
| VLV-03 | Selecting Manual or Automatic MUST submit `set_mode` immediately without a popup. Keep an inline warning visible: *"Changing mode closes all valves first."* (device behavior). The selected mode remains server-reported until fresh confirmation (CTL-05). |
| VLV-04 | `set_output` sends `{"name": "relayN", "state": true|false}`. `set_mode` sends `{"value": "manual"|"automatic"}`. Both MUST be validated against the server's `params_schema` before sending. |
| VLV-05 | Confirmation for `set_output`: the server reports `relayN_*` equal to the requested state **and** `mode == manual`, or the selected output is `always_manual`. Confirmation for `set_mode`: the server reports `mode` equal to the requested value. The app changes no physical-state display optimistically. |
| VLV-06 | Turning a valve ON SHOULD be a single deliberate action (a switch, not a hold). Turning a valve OFF MUST always be possible with one tap whenever CTL-02 allows it. |
| VLV-07 | An **automation panel** MUST show the target humidity, duty (as %), period progress (`automation_elapsed_s` / `automation_period_s` as a progress ring or bar), whether the valve is commanded on, sensor validity and NTP sync. It is visually dimmed and labeled "frozen" in manual mode. |
| VLV-08 | Sensor A and Sensor B temperature/humidity MUST be shown as primary KPI cards. |
| VLV-09 | Until SRV-04/05 exist and the server enables the capabilities, every valve control MUST be rendered disabled with the server's `disabled_reason`. The rest of the tab MUST still be fully functional. |
| VLV-10 | The app MUST NOT expose any RS485 commissioning or firmware-update function. |

---

## 10. UI, UX and visual style (UX)

### 10.1 Navigation

| ID | Requirement |
|---|---|
| UX-01 | **Tabbed layout.** There is one tab per server party, plus an Overview tab and a System tab: **Overview · Pump · Greenhouse · Garage · System**. Tabs are reachable by tapping the tab bar and by swiping horizontally. |
| UX-02 | The party tabs MUST be generated from the server's `parties[]`, in server order. A party not yet known to the app gets a generic tab (SSOT-07). |
| UX-03 | **Overview** shows one compact status card per party: health, the 2–4 headline KPIs, and active controls or alerts. Tapping a card opens that party's tab. |
| UX-04 | **System** shows the server URL and settings, server `/readyz` status, the snapshot `generated_at`, the per-device health table, the session command log, the app version and build info, and the optional update check. |
| UX-05 | The selected tab and scroll positions MUST survive refreshes and app backgrounding. |

### 10.2 Visual style (reference: https://holadelej.hu/)

The reference is a modern data-journalism dashboard. The characteristics to adopt are:

| ID | Requirement |
|---|---|
| UX-10 | **Big-number KPI cards.** The value is set in a large, bold, tabular-figure font, with the unit smaller beside it. (Flet 1.0.3 exposes no font features, so figures are not forced to be tabular; Android's default font has fixed-width digits, so values do not jitter. Revisit if a custom font is added.) Above it is a small **UPPERCASE, letter-spaced label**. Below it is a one-line plain-language caption or context, e.g. "below 0.1 bar → sensor invalid". |
| UX-11 | **Trend and delta indicators.** Show a small ▲ / ▼ / ■ with the change over a window, e.g. "▲ +0.4 °C in 15 min", when history is available (SRV-06 or in-session samples). |
| UX-12 | **Freshness made explicit.** Show "updated 3 s ago" style indicators, as on the reference site ("frissítve 17 perce"). |
| UX-13 | **Restrained palette.** Use neutral surfaces with one accent color. Semantic colors are used only for state: ok / warning / error / stale / disabled. Status MUST NOT be conveyed by color alone; it also needs an icon or text (accessibility). |
| UX-14 | Generous whitespace, a clear typographic hierarchy, no decorative clutter, rounded cards with subtle elevation, Material 3 components. |
| UX-15 | Light and dark themes following the system setting. Both MUST meet WCAG AA contrast. |
| UX-16 | Sparklines or simple line charts with minimal axes and annotations, once history is available. |
| UX-17 | All design tokens (colors, type scale, spacing, radii) MUST be defined in a single `ui/theme.py` and documented in `docs/ui-style-guide.md`. Do not hard-code styles in views. |

### 10.3 Language and accessibility

| ID | Requirement |
|---|---|
| UX-20 | UI language for 1.0 is **English**. All user-facing strings live in one module so a Hungarian translation can be added later. |
| UX-21 | Touch targets are at least 48 dp. The UI supports system font scaling up to 130 % without truncating values. |
| UX-22 | Portrait is the primary orientation. Landscape and tablet SHOULD use a responsive grid. |
| UX-23 | The Garage tab is a daily-use control surface: show one compact row per Garage device with its friendly name, explicitly labeled relay state and a clear Trigger action. Keep lifecycle feedback concise and inline; do not repeat the same state in monitoring cards or device-detail headers. |
| UX-24 | The Android launcher icon and default splash MUST use the supplied Buzsák logo, preserving the artwork with a transparent exterior and an adaptive background color. |

---

## 11. Security (SEC)

| ID | Requirement |
|---|---|
| SEC-01 | 1.0 targets the trusted home LAN. The server now serves HTTPS ([ADR-0003](docs/adr/0003-https-pinned-ca-memory-token.md)). The Android cleartext permission ([ADR-0002](docs/adr/0002-cleartext-http.md)) remains only for the fake server and MUST be removed once the fake server speaks TLS. |
| SEC-02 | The API client MUST send the **bearer token** (`Authorization: Bearer …`) and, for HTTPS, MUST verify the server certificate against the pinned root CA only (`api/trust.py`). A rejected token and an untrusted certificate MUST each show their own message. |
| SEC-03 | After the server accepts an authenticated state request, the app MUST save the bearer token only through Android secure storage backed by Android Keystore; it MUST NOT enter ordinary preferences or logs. The token MUST remain stored until explicit sign-out, app uninstall or OS credential-store loss. The server remains authoritative for expiry and revocation; the app MUST NOT extend or bypass server token lifetime. Fake/live launcher credentials are session-only. |
| SEC-04 | The repository MUST NOT contain secrets, signing keystores or passwords. Release signing material lives outside the repo, and its path is passed through environment variables. |
| SEC-05 | The app MUST NOT log raw server payloads at INFO level or above. |
| SEC-06 | Validate every server response before use. Treat the server as trusted for content but not for well-formedness (SRV-11). |

---

## 12. Build, run and deploy (BLD)

Target environments:

| ID | Environment |
|---|---|
| ENV-01 | Developer machine: **Windows 11**, PowerShell 7 (`pwsh`), VS Code, `uv`, Python ≥ 3.11 and < 3.13. **Developer Mode** MUST be on, because Flutter needs symlink support to build Android apps. |
| ENV-02 | **Android Studio** provides the Android SDK, platform-tools (`adb`), the emulator (AVD) and a JDK (the bundled JBR, or JDK 17). |
| ENV-03 | **Flutter SDK** as required by the pinned Flet version. Flet MAY install it automatically; the version is documented. |
| ENV-04 | Physical Android test device(s). The minimum Android version follows the Flet/Flutter default (documented in `docs/build-and-deploy.md`). |
| ENV-05 | The server is reachable on the LAN at `https://192.168.1.95` (Caddy in front of gunicorn; plain `:8080` is closed). Its preview and production deployments MUST both be selectable by URL. |

Required run, build and deploy options. Each MUST have a PowerShell script in `scripts/` and a VS Code task, and each MUST be documented in `docs/build-and-deploy.md`:

| ID | Option | Typical mechanism |
|---|---|---|
| BLD-01 | **Desktop dev run** with hot reload, for fast UI iteration on Windows 11 | `uv run flet run src/main.py` |
| BLD-02 | **Emulator run.** Start an Android Studio AVD and run the app in it | AVD plus the debug APK installed by `adb`, or the Flet dev app |
| BLD-03 | **Physical device dev run** over USB or Wi-Fi with live reload | `flet run --android` (Flet companion app / QR) or debug APK plus `adb` |
| BLD-04 | **Debug APK build** | `uv run flet build apk` |
| BLD-05 | **Release APK/AAB build**, signed with a keystore taken from environment variables | `flet build apk` / `flet build aab` with signing options |
| BLD-06 | **Install / update on device** over USB or wireless debugging | `adb install -r <apk>`. The script lists devices and lets you pick one |
| BLD-07 | **Device logs**, filtered to the app | `adb logcat` with a filter |
| BLD-08 | **Fake server**: a local mock of the server API with scenario fixtures, for development without the Pi | Small Python server in `tests/` or `scripts/` |
| BLD-09 | **Environment check**: verifies `uv`, Python, Flutter, the Android SDK, the JDK and `adb` devices, and reports what is missing | `scripts/doctor.ps1` |

| ID | Requirement |
|---|---|
| BLD-10 | Builds MUST be reproducible from a clean clone using only the documented steps. Versions are pinned in `uv.lock` and in the docs. |
| BLD-11 | The app version MUST come from one place (`pyproject.toml`). The build number increments on every release build. |
| BLD-12 | Build outputs (`build/`, APKs) MUST be git-ignored. |

---

## 13. Testing (TST)

| ID | Requirement |
|---|---|
| TST-01 | `uv run pytest -q` MUST pass before every commit. |
| TST-02 | Unit tests are required for `domain/` (value parsing, every quality state, frozen-automation logic) and `state/` (store reducers, polling backoff, command lifecycle, timeout to *uncertain*, CTL-02 gating, VLV-02/05). |
| TST-03 | `api/` is tested against JSON fixtures that mirror the server's `/api/dashboard/state`. Fixtures are synthetic; never commit live captures that might contain sensitive data. |
| TST-04 | Time-dependent logic MUST use an injectable clock. |
| TST-05 | Manual acceptance checks per release are listed in `docs/testing.md`: emulator, physical device, and the scenarios offline, stale, automatic mode, and command success/failure/uncertain. |
| TST-06 | **No test may actuate real hardware.** Control tests run against the fake server only. Live control on the real system requires explicit approval from the owner. |

---

## 14. Documentation (DOC)

| ID | Requirement |
|---|---|
| DOC-01 | `README.md` covers what the app is, a quick start (clone → doctor → dev run → device install), and links to the docs. |
| DOC-02 | `docs/architecture.md` covers the layers, data flow, polling, the command lifecycle and module responsibilities, with Mermaid diagrams. |
| DOC-03 | `docs/api-contract.md` covers the snapshot schema exactly as the app consumes it, every SRV item with its current status, and error handling. Update it whenever the server contract changes. |
| DOC-04 | **ADRs** in `docs/adr/NNNN-title.md` record every significant decision: framework, storage, security trade-offs, deviations from this spec. Use the format Context / Decision / Consequences / Status. |
| DOC-05 | `docs/ui-style-guide.md` covers design tokens, components, state colors, and do/don't examples. |
| DOC-06 | `docs/tabs/*.md` describes, for each tab, its KPIs, controls, gating rules and edge cases. |
| DOC-07 | `docs/build-and-deploy.md` covers every BLD option step by step on Windows 11, plus troubleshooting. |
| DOC-08 | `CHANGELOG.md` follows the Keep a Changelog format, updated with every user-visible change. |
| DOC-09 | Every public module, class and function has a concise docstring that cites the relevant requirement IDs. |
| DOC-10 | Code, docs and this specification MUST stay consistent. A change in behavior updates all three in the same change. |

---

## 15. Non-functional requirements (NFR)

| ID | Requirement |
|---|---|
| NFR-01 | From a cold start to the first rendered data (cached) takes ≤ 2 s on a mid-range device. Fresh data appears ≤ 1 poll interval later. |
| NFR-02 | UI interactions respond in ≤ 100 ms. Scrolling and tab switching run at a steady 60 fps on a mid-range device. |
| NFR-03 | Foreground polling every 2 s MUST NOT cause noticeable battery drain or memory growth over 1 hour of continuous use. In-session sample buffers are bounded. |
| NFR-04 | The app MUST NOT crash on malformed or partial server data, network loss, or a server restart. It shows an error state and recovers automatically. |
| NFR-05 | APK size SHOULD stay reasonable for a Flet app; there are no unused heavy dependencies. |

---

## 16. Acceptance criteria (release 1.0)

| ID | Criterion |
|---|---|
| AT-01 | Against the live server (read-only), every party, device, KPI, health field and capability returned by `/api/dashboard/state` is visible in the correct tab, with the correct unit and quality state. |
| AT-02 | Stopping the poller service on the server makes values show as stale within 3 poll intervals. Restarting it recovers them without user action. |
| AT-03 | Disconnecting Wi-Fi shows the offline banner, keeps the last data marked stale, and recovers automatically on reconnect. |
| AT-04 | Against the fake server: valve `set_mode` and `set_output` cover accepted → confirmed, failed (409 automatic mode), and timeout → uncertain, with correct UI states and no optimistic switching. |
| AT-05 | In automatic mode, relay switches are disabled with the hint shown, and the automation panel is active. In manual mode, the automation panel shows "frozen". |
| AT-06 | Against the current server, where the valve capabilities are disabled, the controls show the server's `disabled_reason` and everything else works. |
| AT-07 | Every BLD option works from a clean clone on Windows 11 by following `docs/build-and-deploy.md`. |
| AT-08 | `uv run pytest -q` passes. The docs listed in §14 exist and are current. |

---

## 17. Open decisions

| # | Question | Default until decided |
|---|---|---|
| OD-1 | Exact server command API shape (SRV-04/05). It is owned by the server project. | Assume the proposal in §5 |
| OD-2 | History endpoint and retention on the server (SRV-06) | In-session sparklines only |
| OD-3 | Remote access (Tailscale) and the authentication rollout timing | LAN only |
| OD-4 | App self-update distribution channel (UPD-09) | Manual APK install |
| OD-5 | Hungarian UI localization | English only |
| OD-6 | Default poll interval: 1 s (matches the web dashboard) or 2 s (server spec proposal) | 2 s |
