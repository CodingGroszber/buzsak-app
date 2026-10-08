# Copilot instructions — Buzsák App

These rules apply to every AI assistant and contributor working in this repository. Read them fully before acting.

## 1. What this project is

- **Buzsák App** is an **Android-only** client for the Buzsák garden telemetry and command server.
- The reference server project is `C:\Scripts\Python\buzsak_pi3_server`.
  - It runs on a Raspberry Pi 3 at `192.168.1.95`, with gunicorn/Flask on port `8080`.
  - It polls the LAN devices: garden PLC (PUMP), valve controller (GREENHOUSE) and Sonoff/Matter (GARAGE).
  - It stores everything in SQLite and exposes a JSON API.
- The app shows **all** server KPIs, device health and control signals live, in a tabbed UI.
- In release 1.0, the only controllable signals are **ValveControl** (`set_mode`, `set_output` relay1–4).

## 2. Source of authority

1. **`requirements.md`** in this repo is the specification. Cite requirement IDs (`SSOT-`, `DATA-`, `SRV-`, `ARC-`, `UPD-`, `CTL-`, `VLV-`, `UX-`, `SEC-`, `ENV-`, `BLD-`, `TST-`, `DOC-`, `NFR-`, `AT-`) in docstrings, commits and docs.
2. For server behavior and contracts, `buzsak_pi3_server/requirements.md`, its `docs/` and its code are authoritative. Its `dashboard/queries.py` is the truth for the `/api/dashboard/state` payload. Its `docs/dashboard.md` is partly outdated.
3. If the spec is ambiguous or conflicts with reality, **stop and ask**. Do not silently invent behavior. Record decisions as ADRs in `docs/adr/`.
4. Clearly label statements as *verified fact*, *inference*, *assumption*, *proposal* or *open decision*.

## 3. Non-negotiable rules

- **Single source of truth = server database, accessed only through the server HTTP API.**
  - Never open, copy or sync the SQLite file (server ARC-05).
  - Never call ESP32, PLC or Matter devices directly.
- **No optimistic UI for physical state.** A control shows a new state only after the server reports it. HTTP 2xx means *accepted*, not *confirmed* (CTL-05/06).
- **No automatic command retries.** Retries are explicit user actions with the same idempotency key (CTL-01/04).
- **Keep these states distinct everywhere:** `false`, `0`, `null` / no data, `invalid`, `unavailable` and `stale`. Never render a missing value as `0` or `off` (DATA-02).
- **Valve relays are controllable only when fresh `mode == manual`** and the server capability is enabled (VLV-02, CTL-02). A mode change closes all valves first; submit directly on the explicit segment tap, keep the warning inline, and show only server-reported mode (VLV-03, CTL-05; ADR-0004).
- **Never enable a control the server reports as disabled** (SSOT-08). Show the `disabled_reason`.
- **Never actuate real hardware without explicit owner approval.** This covers tests, scripts and live checks. Use the fake server (BLD-08) by default.
- **Do not modify the server repository** from this project unless the owner explicitly asks. Server-side needs go into `requirements.md` §5 (SRV) and are raised with the owner.
- **No secrets in the repo.** This includes tokens, keystores and passwords. Never log tokens or raw payloads at INFO level or above.
- Ask before destructive or shared-system actions: deploying to the Pi, restarting services, force-pushing, deleting files or branches.

## 4. Tech stack and architecture

- **Python ≥ 3.11 and < 3.13 only** (single stack; dev and APK run 3.12). The UI is **Flet 1.0.3**, pinned exactly. Native Kotlin/Java is allowed only with an ADR.
- **Package and run with `uv`:** `uv sync`, `uv run …`. Do not use `pip install` in the project.
- `flet build` ignores `uv.lock`: pin runtime dependencies with `==` in `[project].dependencies`; build tooling goes in the `dev` group.
- Only pure-Python or Android-wheel packages may be runtime dependencies (they ship inside the APK).
- Layers, with imports pointing downward only:
  - `ui/` → `state/` → `domain/` → `api/`
  - `domain/` and `api/` never import Flet.
  - All HTTP goes through `api/` (SRV-10).
- One-way data flow: poll → immutable snapshot in the store → views re-render. Views dispatch intents and never mutate state.
- All design tokens live in `ui/theme.py`. Do not put inline magic colors or sizes in views (UX-17).
- All user-facing strings live in one strings module (UX-20).
- Settings (server URL, poll interval, timeouts, token) live in `settings.py`. The default URL is `https://192.168.1.95` (Caddy, pinned root CA in `api/trust.py`). The token is kept in memory only (ADR-0003).
- The parameter, capability and party catalogs are **server-driven**. Hard-code only the presentation metadata keyed by id (icons, order, decimals in `domain/presentation.py`; labels and captions in `ui/strings.py`), with a generic fallback (SSOT-07, UX-02).
- `api/` returns the validated JSON object; `domain/snapshot.py` maps it to models. A malformed parameter becomes `INVALID` (never a default value); only a broken top level raises.

## 5. Coding conventions

- `from __future__ import annotations`; frozen dataclasses for domain models; type hints on public APIs.
- Use small, focused modules and functions. Follow YAGNI: no speculative abstractions, plugin systems or DI frameworks.
- Networking is async and never blocks the UI thread. Polls never overlap. Back off exponentially on errors (UPD-04/05).
- Use an injectable clock for all time logic. Server timestamps are UTC; display them in local time.
- Validate every server response. Tolerate unknown fields. Never crash on partial data (SRV-11, NFR-04).
- Docstrings are concise and cite requirement IDs, e.g. `"""Gate valve relay controls (VLV-02, CTL-02)."""`.
- Comments explain only *why*, in one short line.
- Make minimal, targeted changes. Do not refactor unrelated code.

## 6. UI / UX rules

- Use a tabbed layout: **Overview · Pump · Greenhouse · Garage · System**. Party tabs follow the server's `parties[]` order. Tabs support swipe. Tab and scroll positions survive refreshes.
- Use the holadelej.hu-inspired style:
  - big bold tabular numbers with smaller units;
  - small UPPERCASE letter-spaced labels and one-line plain-language captions;
  - ▲ / ▼ / ■ deltas and "updated N s ago" freshness indicators;
  - a restrained palette with one accent; Material 3; light and dark themes; WCAG AA contrast.
- State is never shown by color alone; always add an icon or text.
- Updates are smooth: re-render only changed widgets (use `revision` / `observed_at`), with no flicker or layout jumps, and subtle animations of 250 ms or less.
- Controls give feedback (press state, progress, haptic) within 100 ms, but never change the displayed physical state early.

## 7. Testing

- `uv run pytest -q` must pass before you finish any task (TST-01).
- Unit-test `domain/` and `state/` thoroughly: quality states, frozen automation, CTL/VLV gating, the command lifecycle, and timeout leading to *uncertain*.
- API tests use **synthetic** JSON fixtures that mirror `/api/dashboard/state`. Never commit live captures.
- No test may hit the real server's command endpoints or real devices.

## 8. Build and deploy (Windows 11 + Android Studio)

- Use PowerShell 7 scripts in `scripts/`, each mirrored by a VS Code task. All are documented in `docs/build-and-deploy.md`:
  - `doctor` (environment check);
  - `dev` (desktop hot reload);
  - `emulator`;
  - `device` (live run on a phone);
  - `build-debug` / `build-release` (APK/AAB);
  - `install` (`adb install -r`);
  - `logs` (`adb logcat`);
  - `fake-server`.
- Release signing material comes from environment variables. It is never committed.
- The version is defined only in `pyproject.toml`. `build/` and APKs are git-ignored.
- Before using any Flet CLI flag or API, check the current Flet docs for the pinned version. Do not rely on memory, because the Flet API changes between versions.

## 9. Documentation discipline

- When behavior changes, update the code, `requirements.md` (if the spec changes) and the relevant `docs/` file **in the same change** (DOC-10).
- Update `docs/api-contract.md` whenever the consumed server contract or an SRV status changes.
- Add an ADR for every significant decision or deviation.
- Update `CHANGELOG.md` for user-visible changes.
- Keep `backlog.md` current. Update item status when you start or finish work, and add new items with requirement IDs.
- Do not create ad-hoc summary markdown files to describe your changes.

## 10. Windows / PowerShell environment notes

- Use `pwsh`. Chain commands with `;`. Quote paths that contain spaces.
- Avoid complex multi-line `python -c "..."` commands, because they can hang in continuation mode. Write a temporary script instead.
- If Poetry or uv caches throw `PermissionError`, point the cache to a fresh temp directory for the session instead of fighting ACLs.
- `uv sync` can fail with "incompatible hardlinks (os error 396)" on cloud-filtered profiles; the project sets `link-mode = "copy"` in `[tool.uv]`, so do not remove it.
- `adb` comes from the Android Studio SDK `platform-tools`. Make sure it is on `PATH` or resolve it through `ANDROID_HOME` / `ANDROID_SDK_ROOT`.
- **Android builds on Windows need Developer Mode** (Flutter needs symlinks); it is now on. `scripts/doctor.ps1` reports it. Do not try to enable it yourself: ask the owner.
- Piped `flet build` output on Windows needs `PYTHONUTF8=1`, or Flet's logger crashes on a check mark even when the build succeeded (`build-debug.ps1` sets it).
- To look at the Android emulator, use `adb exec-out screencap -p > file.png`; to drive it, `adb shell input tap/keyevent`. Typing into Flutter text fields this way is fiddly (see `docs/build-and-deploy.md` troubleshooting).
- Reading the live server with plain `GET`s (`/readyz`, `/api/dashboard/state`) is fine and is how the UI was checked. Never send anything else to it (rule in §3).

## 10a. Flet 1.0.3 lessons (verified the hard way)

- Check an API in `.venv/Lib/site-packages/flet` or the docs before using it. The 1.x names differ from older tutorials (for example `ft.Alignment.CENTER`, `ft.Padding.all`, `ft.run`).
- A `Service` such as `ft.SharedPreferences()` attaches to the page only after the page was sent to the client. Calling it earlier raises "Control must be added to the page first". `ui/app.py` shows a placeholder first and uses `wait_until_attached`.
- Even when attached, `SharedPreferences` timed out on desktop (it works on Android). Never let a platform call block startup or a button: wrap it in a timeout and fall back, as `SettingsRepository` does.
- Flet exposes no font features, so there are no forced tabular figures.
- Constructing controls in a test works without a page, so UI structure and in-place updates are unit-tested with a stub page (`tests/test_ui.py`). Visual checks still need a screenshot.
- To look at the desktop app, use `scripts/screenshot-window.ps1 -ProcessName flet`. Match the process name: a title match alone also hits the VS Code window, whose title contains "buzsak_app". `scripts/click-window.ps1` drives it.
- File formatters re-wrap files between edits. Re-read a file before editing it, or an exact-text replacement will fail.

## 11. Current project state

- Specification: `requirements.md` v0.1 (draft). Checkpoint 1 is committed; see `backlog.md` ("Checkpoint 1 summary") for what is verified and what is not.
- Implemented and tested (361 tests): M0/M1 foundations, read-only telemetry UI, HTTPS with a pinned Caddy CA, in-memory bearer token entry, typed valve command client/status watcher, fail-closed Greenhouse controls, dedicated mist/rain automation, sensor and identity panels, and a loopback fake API (`scripts/fake-server.ps1`). Authenticated live readings were checked; relay4 LIGHT on/off round trips through the API (2026-10-07) and live Flet UI (2026-10-08) were confirmed and restored. No water-valve relay or mode command has been sent. Android control UI remains unverified.
- **Verified on the Android emulator (2026-10-06):** build, install, launch, live data from the Pi over plain HTTP, the Overview and System tabs, tab taps, text entry, switching the server address, the offline banner with automatic recovery, and settings persistence across a cold relaunch. `scripts/emulator.ps1`, `build-debug.ps1` and `install.ps1` work.
- **Not yet verified on Android:** the Pump, Greenhouse and Garage tabs, swiping, long-press details, tapping an Overview card, the app-lifecycle pause/resume, dark theme, font scaling, a real phone, `device.ps1` and `deploy.ps1` as a whole (backlog B-134, B-135, B-136, B-151).
- **Known problems:** Android controls are not verified; Windows Developer Mode is currently off, so Android builds fail on symlinks. The app's Python output does not show in `scripts/logs.ps1` (B-149). Flet's `SharedPreferences` never answers on desktop, so settings do not persist there; the repository times out after 3 s and uses defaults (B-116). Token storage is memory-only (ADR-0003, B-302); history is not available (SRV-06). Terminal command re-dispatch semantics remain open (B-211). Valve telemetry was transiently stale/degraded on 2026-10-08 and healthy/fresh on a later read (OBS-04); investigate recurrence. Controls stay fail-closed whenever telemetry is stale.
- Server dependencies:
  - Available: SRV-01 `/api/dashboard/state` and SRV-02 `/healthz` and `/readyz`.
  - Available in server code: valve command endpoints, dispatcher, capability gating (SRV-04/05) and HTTPS/authentication (SRV-07). Live valve telemetry and relay4 capability were verified with an operator token; no other relay/mode command was tested.
  - Missing: history endpoint (SRV-06).
  - Observed on the live server (not requests): stale data with `healthy` devices (OBS-01) and failed Sonoff pulses (OBS-02).
  - Latest verified live valve state (2026-10-08 10:30Z): healthy/fresh. It was transiently stale earlier (OBS-04); do not actuate whenever telemetry is stale.
- Next steps (see `backlog.md`):
  1. Finish the Android checks: the party tabs, swipe, long-press, lifecycle (B-134, B-136, B-151), then make the app's log visible (B-149).
  2. Re-enable Developer Mode, build/install and visually verify Greenhouse controls against the fake server. Keep water-valve relay and mode actuation blocked until separate explicit owner approval (B-307).
  3. Resolve terminal retry semantics with the server developer (B-211); finish command log/poll-rate follow-ups (B-202, B-207, B-208).
