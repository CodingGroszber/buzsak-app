# Backlog — Buzsák App

Work items derived from [requirements.md](requirements.md). Every item cites the requirement IDs it covers.

The specification wins over this file. When the two disagree, fix this file.

- **Status:** `todo` · `doing` · `blocked` · `done`
- **Priority:**
  - `P0` — needed for a read-only MVP
  - `P1` — needed for release 1.0
  - `P2` — later / nice to have
- **Blocked** items name the server dependency (SRV) or open decision (OD) they are waiting on.

Last reviewed: 2026-10-08 (secure token persistence implementation). See the checkpoint summaries below for what is verified and what is not.

---

## Checkpoint 1 summary (2026-10-05, updated 2026-10-06)

**Checkpoint 1 state (2026-10-06):** M0 and the M1 data, state and read-only UI layers were implemented and tested (292 tests passed). The app ran on desktop and on the Android emulator against the live server, checked by screenshot.

**Current state (2026-10-08):** 361 tests pass. The app has pinned-CA HTTPS/auth, direct mode selection with an inline close-all-valves warning, Greenhouse controls and dedicated automation/sensor/identity panels, plus one-command fake/live desktop launchers. Authenticated readings and two relay4 LIGHT on/off round trips (API and live UI) were confirmed and restored to off. A transient stale/degraded snapshot at 10:26 recovered to healthy/fresh by 10:30. No water-valve relay or mode command has been sent. Android UI is not verified; Developer Mode is off.

**Verified on Android (emulator, 2026-10-06):** build and install; live data from the Pi over plain HTTP (cleartext works); the Overview and System tabs; tab tapping; text entry and Save; switching the server address; the offline banner and automatic recovery; settings persistence across a cold relaunch.

**Not yet verified on Android:** the Pump, Greenhouse and Garage tabs, swiping, long-press details, tapping an Overview card, the HIDE/PAUSE and SHOW/RESUME lifecycle handlers, dark theme, font scaling, and a real phone. The full checklist is under [Not yet checked on Android](#not-yet-checked-on-android); it points to B-134, B-135, B-136, B-149, B-151, B-152, B-153 and B-154.

**Resolved blocker:** Windows Developer Mode was off, so `flet build apk` failed at the Gradle step (*"Building with plugins requires symlink support"*). The owner enabled it on 2026-10-06 and the build now works. `scripts/doctor.ps1` checks for it.

**M1 exit criteria status**

| Criterion | Status |
|---|---|
| AT-01 every KPI visible in the right tab with unit and quality state | Partly: Overview and Greenhouse checked by screenshot on desktop, Overview and System on Android; the Pump, Greenhouse and Garage party tabs on Android are still unchecked |
| AT-02 stopped poller shows stale values, recovers without user action | Observed for real: on 2026-10-05 the Pi's data was 26 h to 51 h old and the app flagged it (OBS-01); by 2026-10-06 the Pi was updating again and the warning disappeared on its own |
| AT-03 offline banner, last data kept, automatic recovery | Met on Android: a network drop and a closed-port address both showed the banner with the old data kept, and the app recovered by itself |
| AT-06 disabled valve controls show the server's reason | Not started: valve controls belong to M2 |

**Findings to act on**

1. The app's Python output does not appear in `scripts/logs.ps1` (B-149).
2. On desktop, Flet's `SharedPreferences` never answers, so settings do not persist there; on Android they do (B-114, B-116).
3. On 2026-10-05 the Pi's data was 26 h (PUMP, GARAGE) and 51 h (GREENHOUSE) old while every device reported `healthy` (OBS-01); it was fresh again on 2026-10-06. Worth knowing why it stopped. Server-side, for the owner.
4. Both Sonoff devices report their last pulse as failed (`Node 1 is not (yet) available`) (OBS-02). Read from the live payload; not investigated.

---

## Checkpoint 2 summary (2026-10-08)

**State:** 361 tests pass. The Greenhouse screen now follows the device page's narrow, single-column layout: Manual/Automatic segments, four current-state relay buttons with Mist/Rain hints, mist and rain automation, sensor health/readings, and firmware/IP. Mode changes submit directly on segment tap with an inline warning that all valves close; the displayed mode remains server-reported. Command states show an emoji, semantic color and text.

**Verified live:** authenticated Pi state and capability reads; relay4 LIGHT was turned on from the app UI, server-confirmed with fresh telemetry, then restored to off and confirmed. No mode command or water-valve relay command was sent. The relay click issue was an async Flet callback wrapped in a lambda; binding the async event handler directly fixed it. A transient stale/degraded valve snapshot was observed and later recovered (OBS-04).

**Current live observation:** the last inspected Greenhouse screen showed mode `automatic` and Mist `open`, as reported by the server. This is the controller's automatic state, not an app-issued command; the app was left in LIVE SERVER mode and no control was touched afterward.

**Still open:** Android Greenhouse UI/build verification is blocked while Windows Developer Mode is off (B-134, B-307). Water-valve relays and mode actuation remain untested. Command re-dispatch after a terminal failure remains unresolved (B-211); haptics, tighter in-flight polling and a session command log remain (B-202, B-207, B-208).

## Checkpoint 3 summary (2026-10-08)

**State:** 378 tests pass. The Garage tab has compact Right/Left Trigger rows with fail-closed per-device health/quality/capability gating, concise lifecycle feedback, and server-snapshot status. The loopback fake server verifies pending-to-succeeded, cooldown, and stale/offline rejection without hardware access.

**Verified live:** one explicitly approved `sonoff-2` pulse was accepted as request 4. A later GET reported `last_pulse=succeeded`, with no error; device health was healthy and `on_off` remained false. This confirms the pulse lifecycle only, not garage-door position. No Garage Right pulse was sent.

**Still open:** Android Garage UI verification and the broader Android checks remain unverified (B-134, B-136, B-151). No live Garage Right pulse has been sent. The repeated desktop `SharedPreferences` timeout remains tracked by B-116.

## Checkpoint 4 summary (2026-10-08)

**State:** 378 tests pass. Bearer credentials now load/save via pinned Flet Secure Storage, backed by Android Keystore. A token is remembered only after a valid authenticated state snapshot; explicit Sign out removes it. Ordinary preferences and logs remain token-free, and Android backup is disabled for the Keystore entry.

**Still open:** Build/install this version and verify save, force-stop/relaunch persistence, invalid-token behavior, and Sign out on a physical Android device (B-302, B-154). The server may still expire or revoke credentials.

---

## Milestones

| Milestone | Goal | Exit criteria |
|---|---|---|
| **M0 Foundation** | Toolchain, skeleton and decisions in place | `doctor` passes, desktop dev run shows the app, ADR-0001 accepted. **Met**, except that `doctor` now correctly reports Developer Mode as FAIL |
| **M1 Read-only MVP** | All KPIs live in tabs against the real server | AT-01, AT-02, AT-03, AT-06 |
| **M2 Valve control** | ValveControl working end-to-end against the fake server | AT-04, AT-05 |
| **M3 Release 1.0** | Signed APK, documentation complete | AT-07, AT-08; valve control live once SRV-04/05 ship and the owner approves |
| **M4 Post-1.0** | Enhancements | — |

---

## M0 — Foundation

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-001 | Write ADR-0001 "UI framework: Flet". Cover the alternatives and pin a version after checking the current Flet docs | ARC-01, ARC-02, DOC-04 | P0 | done |
| B-002 | Add Flet and `httpx` (or equivalent) to `pyproject.toml`, add the `[tool.flet]` section, run `uv lock`. Confirm `uv_build` works with `flet build`, otherwise write an ADR | ARC-02, ARC-03, BLD-10 | P0 | done (`flet build apk` produces a 128 MB APK with `httpx` for arm64-v8a, armeabi-v7a and x86_64; it runs on the emulator; first Gradle run took 433 s) |
| B-003 | Create the package skeleton `api/ domain/ state/ ui/ settings.py` and the `src/main.py` entry point. Add an import-direction test (`domain`/`api` must not import `flet`) | ARC-04, ARC-05 | P0 | done |
| B-004 | Write `scripts/doctor.ps1`. It checks uv, Python, Flutter, the Android SDK, the JDK and `adb devices`, and prints fixes | BLD-09, ENV-01..04 | P0 | done |
| B-005 | Write `scripts/dev.ps1` and a VS Code task for the desktop hot-reload run | BLD-01 | P0 | done |
| B-006 | Set up `.gitignore` (`build/`, `*.apk`, `*.aab`, keystores, `.venv`) and `CHANGELOG.md` | BLD-12, SEC-04, DOC-08 | P0 | done |
| B-007 | Set up the pytest harness: `tests/` and the injectable `Clock` | TST-01, TST-04 | P0 | done |
| B-008 | Write `docs/build-and-deploy.md` v0: toolchain install on Windows 11 (Android Studio SDK, Flutter, JDK, `ANDROID_HOME`) | DOC-07, ENV-01..04 | P0 | done |

## M1 — Read-only MVP

### Data and API

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-101 | Add synthetic fixtures mirroring `/api/dashboard/state`. Cover all parties, all quality states, `has_data=false`, stale values, an unconfigured Matter party, and disabled capabilities | TST-03, SRV-01 | P0 | done |
| B-102 | Build the `api/` client: async GET for the state endpoint and `/healthz` / `/readyz`. Support timeouts, an optional bearer token and HTTPS URLs; tolerate unknown fields; use typed errors | SRV-01, SRV-02, SRV-10, SRV-11, SEC-02 | P0 | done |
| B-103 | Build the `domain/` models (frozen): Snapshot, Party, Device, Health, Parameter, Capability, LastPulse | ARC-07, DATA-01 | P0 | done |
| B-104 | Implement value parsing from `value`/`value_type` into typed values. Distinguish good / stale / unavailable / invalid / no-data / `false` / `0`; never default silently | DATA-01, DATA-02 | P0 | done |
| B-105 | Add the presentation catalog: icons, order and decimals keyed by `parameter_id` in `domain/presentation.py`, labels and captions in `ui/strings.py` (UX-20), with a generic fallback for unknown ids. Display `ratio` as % | SSOT-07, DATA-03, UX-10, UX-20 | P0 | done |
| B-106 | Add frozen-automation logic: `automation_*` values are marked frozen when `mode == manual` | DATA-02, VLV-07 | P0 | done |

### State and polling

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-111 | Build the store: immutable snapshot replacement and a per-parameter change diff (`revision` / `observed_at`) | ARC-06, UPD-07 | P0 | done (`state/store.py`, `state/diff.py`) |
| B-112 | Build the polling service: interval from settings, no overlapping polls, exponential backoff capped at 30 s, pause and resume with the app lifecycle | UPD-01, UPD-03, UPD-04, UPD-05 | P0 | done (`state/poller.py`, wired in `ui/app.py`; polling, backoff and automatic recovery verified on Android; the HIDE/PAUSE and SHOW/RESUME lifecycle handlers are not yet exercised, see B-151) |
| B-113 | Add a connection-state model (connecting / online / offline / server unhealthy) and the "last updated N s ago" freshness value | UPD-05, UPD-06 | P0 | done (`state/connection.py`) |
| B-114 | Persist settings with Flet client storage: URL, poll interval, timeouts | ARC-09 | P0 | done on Android (a saved address survived a force-stop and cold relaunch). On desktop the storage call still never answers, so settings do not persist there. The token uses separate secure storage (B-302) |
| B-115 | Cache the last snapshot for instant startup, shown as *cached* until a fresh fetch arrives | SSOT-05, NFR-01 | P1 | todo |
| B-116 | Find out why Flet's `SharedPreferences` never answers on desktop (`Timeout waiting for invoke method listener`, even though the service is attached to the page). It works on Android (see B-114), so this is now only a desktop-development inconvenience: the app waits 3 s at start, then uses defaults | ARC-09, NFR-04 | P2 | todo (cause unknown; a throwaway probe could not be run) |

### UI

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-121 | Create `ui/theme.py` with tokens (palette with one accent, type scale with tabular figures, spacing, radii), light and dark themes, WCAG AA | UX-13..UX-17 | P0 | doing (accent seed, warning amber per brightness, spacing, radii, type scale; not yet a WCAG contrast check and no tabular figures: Flet 1.0.3 exposes no font features, Roboto digits are fixed-width) |
| B-122 | Create the strings module (English) | UX-20 | P0 | done |
| B-123 | Build the KPI card component: big number, unit, UPPERCASE label, caption, quality badge (icon and text), details on tap (`observed_at`, `last_changed_at`) | UX-10, UX-12, UX-13, DATA-02, DATA-04 | P0 | done (`ui/components.py`, `ui/view_models.py`; verified on desktop against the live server; details show on long-press via the tooltip, unverified on a touchscreen) |
| B-124 | Build the boolean/state tile and the device health chip | DATA-05, UX-13 | P0 | done (`StatusChip`, health chip per device) |
| B-125 | Build the tab shell: Overview · server-driven party tabs · System. Support swipe; keep the tab and scroll positions | UX-01, UX-02, UX-05 | P0 | done (tabs generated from `parties[]`, selected tab kept across rebuilds; swipe not yet tried on a touchscreen) |
| B-126 | Add the global connection banner and the freshness indicator | UPD-05, UPD-06 | P0 | done (connection chip, banner, "updated N s ago", and a warning when the server's own data is old, `domain/staleness.py`) |
| B-127 | Build the **Pump** tab: pumps, switches, LEDs, pressure, and water level with a reliability note. `set_output` is shown disabled with its reason | §4.2, SSOT-08 | P0 | done (generic read-only cards; `set_output` is not shown as a control yet) |
| B-128 | Build the **Greenhouse** tab (read-only part): sensor A/B cards, relay states, mode, automation panel (progress ring, frozen state) | VLV-07, VLV-08 | P0 | doing (all KPI cards shown, automation values dimmed and flagged *Frozen* in manual mode; no progress ring and no relay controls yet) |
| B-129 | Build the **Garage** tab: compact Right/Left relay-state rows and pulse controls | §4.2, §4.3, CTL-11, UX-23 | P0 | done (both controls and loopback lifecycle verified; live app action confirmed by owner on Garage Left; no live Right pulse sent) |
| B-130 | Build the **Overview** tab: one card per party with headline KPIs and alerts; tapping a card opens its tab | UX-03 | P0 | done (`ui/overview_tab.py`, headline KPIs from `domain/presentation.py`) |
| B-131 | Build the **System** tab: settings editor, `/readyz`, `generated_at`, health table, app version | UX-04 | P0 | doing (server address editor, connection facts and app version; no `/readyz` call or per-device health table; version is blank in a packaged app) |
| B-132 | Implement diff-based re-rendering (update only changed controls) and value-change animations of 250 ms or less | UPD-07, NFR-02 | P1 | doing (cards update in place from the diff, tested; opacity animation only; frame rate unmeasured) |
| B-134 | Check the UI on a touchscreen: swipe between tabs, long-press details, tap an Overview card, keyboard for the address field, safe areas, font scaling to 130 % | UX-01, UX-21, UX-22, DATA-04 | P0 | doing (on the emulator: tab tap, text field with the software keyboard, Save button and the Overview layout work; swipe, long-press details, tapping an Overview card, font scaling and a real phone are not yet checked) |
| B-135 | Check light and dark themes visually and measure WCAG AA contrast of the tone colours, the dimmed values and the badges | UX-13, UX-15 | P1 | todo |
| B-136 | Look at the Pump, Garage and System tabs by screenshot (only Overview and Greenhouse were on desktop; on Android: Overview and System) | AT-01 | P0 | doing (Pump, Greenhouse and Garage party tabs still unchecked on Android) |
| B-137 | Try the offline path for real: cut the network, check the banner, kept data and recovery | AT-03, UPD-05 | P0 | done on Android (an unplanned emulator network drop and a closed-port address both showed "Server unreachable" with the banner, kept the old data marked as out of date, and recovered without action); a deliberate outage against the fake server (B-141) is still worth adding |
| B-133 | Show in-session sparklines and ▲/▼/■ deltas from bounded in-memory samples, labeled "this session only" | UX-11, SRV-06, NFR-03 | P2 | todo |

### Tooling and docs

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-141 | Build the fake server (`scripts/fake-server.ps1` plus Python simulator). Scenarios: normal, stale, offline device, automatic/manual mode, malformed payload | BLD-08, TST-06 | P0 | done (normal, stale, offline, malformed, device failure, uncertain and slow confirmation scenarios; one-command desktop preview and VS Code task) |
| B-142 | Write `scripts/emulator.ps1` (start an AVD, wait for boot) | BLD-02 | P0 | done (booted `Medium_Phone_API_36.1` and waited for `sys.boot_completed`) |
| B-143 | Write `scripts/device.ps1` (live run with `flet debug android`) | BLD-03 | P0 | written, not yet run |
| B-144 | Write `scripts/build-debug.ps1`, `install.ps1`, `logs.ps1` and `deploy.ps1` | BLD-04, BLD-06, BLD-07 | P0 | doing (build, install and launch verified on the emulator; fixed a UTF-8 crash in Flet's logger that made a good build report failure; `logs.ps1` shows nothing for the app's Python output, see B-149; `deploy.ps1` as a whole not yet run) |
| B-145 | Configure Android cleartext HTTP; write an ADR (cannot be scoped to one host) | SEC-01, DOC-04 | P0 | done (ADR-0002; flag verified in the generated manifest, and live HTTP to the Pi works on Android) |
| B-146 | Write `docs/architecture.md`, `docs/api-contract.md`, `docs/ui-style-guide.md` and `docs/tabs/*.md` | DOC-02, DOC-03, DOC-05, DOC-06 | P1 | doing (`docs/api-contract.md` and two ADRs exist; the rest is todo) |
| B-147 | Turn on Windows Developer Mode, then run the build on the emulator | BLD-02..BLD-04, BLD-06 | P0 | done (owner enabled it; symlink test passes; APK built, 128 MB) |
| B-148 | Document the two desktop dev aids `scripts/screenshot-window.ps1` and `scripts/click-window.ps1` (capture and click the Flet window) in `docs/build-and-deploy.md`, or drop them | DOC-07 | P2 | todo |
| B-149 | Make the app's Python output visible with `scripts/logs.ps1`. The tag `flet.python` from the Flet docs produced nothing on the emulator, so either the output goes elsewhere or no warning was logged. Check with a deliberate `logging.warning`, and read `console.log` via `StoragePaths` if needed | BLD-07 | P1 | todo |
| B-150 | System tab polish seen on Android: the "Server" label appears twice, the address field is not full width, and the app version shows a dash | UX-04, B-303 | P2 | todo |
| B-151 | Exercise the app-lifecycle handlers on Android: send the app to the background and back (`adb shell input keyevent KEYCODE_HOME`, then relaunch) and confirm polling pauses and resumes at once, with no request while hidden | UPD-03 | P1 | todo |
| B-152 | Run `scripts/deploy.ps1` as a whole (build, install and launch in one step, with `-SkipBuild` and `-Logs`). Build, install and launch were verified separately, never chained | BLD-04, BLD-06 | P1 | todo |
| B-153 | Run `scripts/device.ps1` (`flet debug android`) on the emulator and confirm the live-run workflow, including how edits reach the device. It is written from the Flet docs and has never been run | BLD-03 | P1 | todo |
| B-154 | Run the app on a **real phone**: USB debugging on, device shows as `device` in `adb devices`, phone on the same Wi-Fi as the Pi, then `deploy.ps1 -Serial <id>`. Covers real touch (swipe, long-press), real Wi-Fi networking, real font scaling and safe areas. The emulator reaches the LAN through the host, which a phone does not | BLD-03, BLD-06, UX-21, UX-22 | P0 | todo (needs the owner's phone) |

### Not yet checked on Android

Verified on the emulator on 2026-10-06: build, install, launch, live data over plain HTTP, the Overview and System tabs, tab taps, text entry, switching the server address, the offline banner with recovery, and settings persistence. Everything below is **not** verified. Tick an item here when the item it points to is done.

| Done | Area | What to check | Tracked in |
|---|---|---|---|
| [ ] | Pump tab | Cards for pressure, water level, pumps, switches and LEDs; units, states and the water-level caption | B-136 |
| [ ] | Greenhouse tab | Sensor A/B, relays, mode and automation cards; automation values dimmed and flagged *Frozen* when the mode is manual (needs the fake server or a manual-mode device) | B-136, B-141 |
| [ ] | Garage tab | Compact Right/Left relay state and Trigger rows; concise lifecycle feedback | B-136 |
| [ ] | Swiping between tabs | Horizontal swipe changes tab and the tab bar follows | B-134 |
| [ ] | Long-press details | Long-press on a card shows the tooltip with observed and changed times | B-134 |
| [ ] | Tapping an Overview card | Opens that party's tab | B-134 |
| [ ] | Background and foreground | Polling pauses when hidden and resumes at once on return; no requests while hidden | B-151 |
| [ ] | Dark theme | Switch the emulator to dark mode; check legibility and contrast of tones, badges and dimmed values | B-135 |
| [ ] | Font scaling | System font size at 130 %: no truncated values, cards still tidy | B-134 |
| [ ] | Safe areas and rotation | Cutouts, status bar and navigation bar; landscape does not break the layout | B-134 |
| [ ] | `deploy.ps1` as a whole | Build, install and launch chained, with `-SkipBuild` and `-Logs` | B-152 |
| [ ] | `device.ps1` live run | `flet debug android` on the emulator | B-153 |
| [ ] | App log in `logs.ps1` | A deliberate log line from the app shows up | B-149 |
| [ ] | A real phone | All of the above on physical hardware over Wi-Fi | B-154 |

## M2 — Valve control

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-201 | Make the command API client match the server contract: submit with an idempotency key, read status, cancel pending. Keep endpoint paths in one place | SRV-04, SRV-05, CTL-01 | P1 | done (`api/client.py`, `api/endpoints.py`; fake transport tests) |
| B-202 | Build the command lifecycle: sending → pending → acknowledged → confirmed / failed / expired / uncertain. No automatic resend; one in-flight command per device | CTL-03..CTL-06, CTL-08 | P1 | doing (Runtime submits once and polls; timeout becomes uncertain; status-only check tested; session log remains) |
| B-203 | Implement gating: server capability, healthy device, fresh relevant values and mode, per-output controllability/`always_manual`, one in-flight command, plain-language reason | CTL-02, VLV-02, VLV-09, SSOT-08 | P1 | done (unit-tested; live relay4 gate also verified during the approved round trip) |
| B-204 | Validate params against `params_schema` before sending | VLV-04 | P1 | done (fail-closed schema validation in Greenhouse controls) |
| B-205 | Build the mode control; submit on tap and keep the all-valves-close warning inline | VLV-01, VLV-03 | P1 | done (direct submit; popup removed per ADR-0004) |
| B-206 | Build relay controls: visual busy feedback, no optimistic state, inline lifecycle, explicit safe recovery | VLV-01, VLV-05, VLV-06, CTL-07, CTL-10 | P1 | doing (emoji/color lifecycle and live UI relay4 path verified; haptics remain; terminal retry contract tracked by B-211) |
| B-207 | Refresh server state immediately after a confirmed command; tighten polling while a command is in flight | UPD-08 | P1 | doing (`poll_now()` on confirmation; interval tightening remains) |
| B-208 | Add the session command log on the System tab | CTL-09 | P1 | todo |
| B-209 | Add fake-server command scenarios: success, 409 automatic mode, failure, no confirmation (uncertain), slow ack | AT-04, TST-06 | P1 | doing (loopback fake API tests acceptance, interlock, failure, idempotency and slow confirmation; app timeout/status-check path tested in-process) |
| B-210 | Test full gating and lifecycle logic: VLV-02/05, CTL-02/05/06 | TST-02 | P1 | done (schema, freshness, mode exception, disabled capability, uncertain lock, status check, automation, sensors and rain quality tested) |
| B-211 | Resolve terminal retry semantics: the app spec calls for same-key retry, while server deduplication returns the original terminal command; define a safe re-dispatch contract | CTL-01, CTL-04, SRV-04, SRV-05 | P1 | blocked (no re-dispatch implemented) |

## M3 — Release 1.0

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-301 | Write `scripts/build-release.ps1`: signed APK/AAB with keystore and passwords from environment variables, build number increment | BLD-05, BLD-11, SEC-04 | P1 | todo |
| B-302 | Persist the verified bearer token in Android Keystore-backed secure storage until sign-out or uninstall | SEC-03 | P1 | doing (secure store, authenticated-save gate and sign-out implemented; physical-device persistence/restart test remains) |
| B-303 | Add the app icon, splash screen and version/build info on the System tab | UX-04, UX-24 | P1 | partial (launcher/splash icon implemented; System version/build info remains) |
| B-304 | Write the manual acceptance checklist in `docs/testing.md` and run it on the emulator and a physical device | TST-05, AT-01..AT-08 | P1 | todo |
| B-305 | Check performance and battery: one hour of foreground polling with no memory growth; measure cold start | NFR-01..NFR-03 | P1 | todo |
| B-306 | Finish the README quick start and the `docs/build-and-deploy.md` troubleshooting section; verify a clean-clone build | DOC-01, DOC-07, BLD-10, AT-07 | P1 | todo |
| B-307 | **Live valve control on real hardware.** Requires a valid operator token, the server enabling the capabilities, Android verification and explicit owner approval for each control scope | VLV-*, TST-06 | P1 | partial: relay4 LIGHT round trips confirmed/restored by API (2026-10-07) and live UI (2026-10-08); water-valve relays and mode remain untested; Android verification blocked (Developer Mode off) |
| B-308 | **Garage Left live pulse check.** Require fresh healthy telemetry and enabled capability; send one pulse only and observe `last_pulse` | CTL-11, TST-06 | P1 | done (2026-10-08: fresh healthy preflight, one accepted request, then `last_pulse=succeeded`; relay remained false; no retry) |
| B-309 | **Garage Right live pulse check.** Require fresh healthy telemetry and enabled capability; send one pulse only and observe `last_pulse` | CTL-11, TST-06 | P1 | todo (not sent; requires explicit owner approval for live Garage Right actuation) |

## M4 — Post-1.0

| # | Item | Reqs | Prio | Status |
|---|---|---|---|---|
| B-401 | Add history charts once the server provides a history endpoint | SRV-06, UX-16 | P2 | blocked (SRV-06, OD-2) |
| B-402 | Switch to `/api/v1/state` when it is available | SRV-03 | P2 | blocked (SRV-03) |
| B-403 | Add authentication and HTTPS: token entry UI, viewer/operator role handling | SRV-07, SEC-02, SEC-03 | P2 | doing (HTTPS with the pinned CA and a masked token field are done and checked against the live server without a token; a real token, Android and role handling are not) |
| B-404 | App update check through a version manifest; open the installer | UPD-09 | P2 | blocked (OD-4) |
| B-405 | Remote access over Tailscale | §2.3 | P2 | blocked (OD-3) |
| B-406 | Hungarian localization | UX-20 | P2 | blocked (OD-5) |
| B-407 | PLC pump control and the garage pulse from the app | §2.3 | P2 | todo (needs approval) |
| B-408 | Push notifications (device offline, low water) and a home-screen widget | §2.3 | P2 | todo |
| B-409 | Responsive tablet/landscape grid | UX-22 | P2 | todo |
| B-410 | Show per-device health detail on the System tab, and an in-app explanation when a server reports `healthy` but its data is old | DATA-05, UX-04 | P2 | todo |

---

## Server-side requests (owned by `buzsak_pi3_server`)

These are tracked here for visibility only. **Do not implement them from this repo** (see copilot-instructions §3). `OBS-*` rows are things observed on the live server, not requests. The full request to the server developer, with phasing, contracts and open questions, is [change_proposal.md](change_proposal.md).

| SRV | Need | Server ref | Status |
|---|---|---|---|
| SRV-03 | Versioned `/api/v1/state` | API-01 | open |
| SRV-04 | Valve command submission (`set_output`, `set_mode`) with an idempotency key | CMD §9, API-09 | **implemented in server code** (`POST /api/v1/devices/{id}/commands`, read 2026-10-07); relay4 LIGHT round trip exercised live; water valves/mode remain untested |
| SRV-05 | Command status and lifecycle endpoint | CMD §9 | **implemented in server code** (`GET`/`DELETE /api/v1/commands/{id}`); not exercised live |
| SRV-06 | History / time-series endpoint and retention | API-02, DB-08 | open |
| SRV-07 | Bearer authentication, roles, HTTPS | SEC-02/04/05/06 | **done on the server** (verified 2026-10-07: HTTPS via Caddy, `401` without a token); the app side is B-403 |
| SRV-08 | Push channel (SSE / WebSocket) | — | not planned |
| OBS-01 | Observed on 2026-10-05: all 26 parameters were `stale` (newest observation 26 h old for PUMP and GARAGE, 51 h for GREENHOUSE) while every device's health said `healthy`. Health is not derived from observation age, and the poller may have stopped. Owner to check the Pi; the app already warns (`domain/staleness.py`) | POL-11, health | observed, owner to investigate |
| OBS-02 | Observed on 2026-10-05: both Sonoff devices report `last_pulse` as failed with `Node 1 is not (yet) available` | DEV-09, DEV-10 | observed, not investigated |
| OBS-03 | Verified 2026-10-06: the server's valve adapter rejects the controller's current firmware v0.9 payload (`automation: missing required field 'valve'`; `automation` is now nested `mist` / `rain`). The Pi reports `valve-controller` offline with 71 failures. Reproduced by feeding the live device payload to the server's own `parse_state()` (read-only). Details and fix in [change_proposal.md](change_proposal.md) CP-01 | DEV-01, DEV-05, POL-04 | fixed in server code (nested parsing, read 2026-10-07); live recovery to confirm with a token |
| OBS-04 | Authenticated GET at 10:26Z on 2026-10-08: `valve-controller` health was `degraded`, `stale=true`, consecutive failures 0 and no last error. `mode`, relay states and relay4 capability flags had `quality=good` but `stale=true`. A subsequent GET at 10:30Z and the live UI test saw healthy/fresh telemetry. Investigate the transient Pi poller/health freshness gap; app must not bypass stale telemetry by calling the ESP32 directly. | POL-04, POL-07, POL-11, CMD-05 | observed, recovered by 10:30Z; server-side investigation needed |
| SRV-13 | Valve controller data parity: rain automation parameters, per-relay `controllable` / `always_manual`, sensor error details, firmware. [change_proposal.md](change_proposal.md) CP-02..CP-04 | DEV-02, DEV-03, DEV-05 | **implemented and live values verified** (2026-10-07/08); freshness issue tracked by OBS-04 |
| SRV-14 | Command execution for the valve controller (storage, dispatcher, capability enablement, simulated device tests). [change_proposal.md](change_proposal.md) CP-05..CP-08, CP-12; extends SRV-04/05 | CMD §9, DEV-04 | **implemented in server code**; `control.valve_enabled` is verified active for relay4 LIGHT; other relay/mode command scopes remain untested |

## Open decisions

See [requirements.md §17](requirements.md) (OD-1 … OD-6). When one is resolved, record an ADR and unblock the items that depend on it.
