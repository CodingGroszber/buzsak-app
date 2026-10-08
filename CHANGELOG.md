# Changelog

All notable user-visible changes. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows `pyproject.toml` (BLD-11).

## [Unreleased]

### Added
- Android launcher icon and splash artwork derived from `assets/app_logo.jpg`, with a transparent exterior and navy adaptive-icon background (UX-24).
- Remembered bearer authentication using Android Keystore-backed secure storage after successful server authentication, with explicit Sign out and no token in ordinary preferences (SEC-03, ADR-0006).
- Compact Garage Right/Left Trigger rows with explicit relay labels, semantic state styling, concise lifecycle feedback and snapshot-only confirmation (CTL-11, UX-23).
- Dedicated Greenhouse automation and sensor sections: mist target/duty/cycle progress, frozen automation state, rain schedule/last run, Sensor A/B status/measurements/frame age/errors, and firmware/controller IP. Live readouts were checked against the authenticated server state.
- Greenhouse mode and relay controls, gated by server capability, healthy device state, fresh mode/output metadata and the firmware's `always_manual` exception. Mode changes submit on tap with a persistent inline valve-close warning; relay/mode state remains server-reported.
- Inline command lifecycle messages now use a state-specific emoji and semantic color; live relay-button event dispatch is fixed and the LIGHT UI round trip was confirmed/restored.
- Valve command submission and status polling, with UUID idempotency keys, an explicit same-key retry only after an ambiguous submit, uncertain timeout handling and GET-only status checks. Inline lifecycle states use emoji and semantic colors.
- A loopback fake server and VS Code task for exercising telemetry and simulated commands without a token from, or network path to, the Pi/device.
- Session-only live desktop launcher (`scripts/dev.ps1 -LiveServer`) retrieves the provisioned operator token over SSH without printing or persisting it; the app clearly marks this connection as LIVE SERVER.
- One-command desktop preview (`scripts/dev.ps1 -FakeServer`) that starts the local fake API and preloads its fake URL/token in memory; no System-tab credential typing required.
- HTTPS to the server with a pinned root CA, a masked access-token field on the System tab, and a "Sign-in needed" state when the token is missing or rejected.
- Separate messages for an untrusted certificate and a server that requires HTTPS.
- Live read-only UI: connection status, "updated N s ago", tabs generated from the server's parties (Overview, Pump, Greenhouse, Garage, System), KPI cards with value, unit, state badge and long-press details, and an editable server address.
- Warnings when the server is unreachable or answering badly, and when the server's own data is old although it answers.
- Frozen automation values are dimmed and labelled while the valve controller is in manual mode.
- Android deploy scripts: emulator, live run, build, install, deploy and logs (not yet run end to end).
- Project skeleton: layered package (`api`, `domain`, `state`, `ui`), theme tokens, settings defaults.

### Known issues
- The default address is now `https://192.168.1.95`; the retired `http://192.168.1.95:8080` saved by older builds is replaced on load.
- Settings do not persist on desktop (Flet storage does not answer there); they persist on Android.
- The app's Python output does not show in `scripts/logs.ps1` yet.
- Android builds need Windows Developer Mode.
- The live relay4 LIGHT command path has been verified with an operator token and restored to off. Water-valve relay/mode commands remain untested; Android control UI remains unverified.
- The server deduplicates a repeated idempotency key to the original terminal command, so re-dispatch after a definitive failure remains open (B-211).
