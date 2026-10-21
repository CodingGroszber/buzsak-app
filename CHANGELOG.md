# Changelog

All notable user-visible changes. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning follows `pyproject.toml` (BLD-11).

## [Unreleased]

### Added
- Dense, Manual-only Greenhouse daily Rain schedule editor matching the controller's HH:MM / 1..60 minute Apply form. Inputs and Apply share one compact row; explanatory helper copy and empty feedback space are omitted. Uses the separately gated server action, manual/idle/fresh prerequisites, preserved drafts, inline actionable status and GET-only ambiguity recovery; no automatic mode change, app-side scheduler or live schedule write (VLV-11, UX-27, SRV-17).
- Pump **Fill tank** action through the server's PLC v4.1 refill command, fail-closed AUTO/idle/level/capability gates, single submission and GET-only uncertain-status recovery; no direct pump-output controls or live refill actuation (CTL-12, SRV-16).
- Separate phone-local pending alert occurrences with explicit Android Acknowledge actions and restoration after relaunch/reboot; no server persistence. Native unit tests pass; device acceptance is pending (NTF-15/16, ADR-0010).
- Reproducible, secret-scanned local Repomix reference export via `scripts/repomix.ps1` and its VS Code task (DOC-11).
- Settings tab after System, containing server/token/sign-out; System is now read-only diagnostics (UX-01, UX-04).
- Phone-local custom-alert editor, validated rule storage, numeric comparisons and tested session evaluator; bounded Android foreground-service/local-notification bridge source and Runtime wiring. Native build and device delivery verification are pending (NTF-01..NTF-14, ADR-0009).
- Android launcher icon and splash artwork derived from `assets/app_logo.jpg`, with a transparent exterior and navy adaptive-icon background (UX-24).

### Changed
- Pump tank-level and pressure readouts now match Greenhouse's compact status/name/value sensor rows, with healthy/fault/quality indicators driven by the corresponding fresh server validity flags; raw diagnostics stay hidden and refill gating is unchanged (UX-29).
- Greenhouse Sensors now precede Automation, with compact unframed status/name/temperature–humidity rows, paired readings and routine age metadata in tooltips. Explicit fault/quality indicators remain; mist target/duty also share a row (VLV-08, UX-28).
- Unified Pump/Greenhouse headers with muted firmware/IP and health, no raw device-name heading or duplicate identity footer. Greenhouse content now shrink-wraps and hides empty fallback grids instead of retaining a trailing wrapping firmware row (UX-26).
- Pump now matches Greenhouse's narrow responsive sections and compact quality-aware tank/pressure and PLC-state readouts. Sensors/Diagnostics and the redundant `garden-plc` heading are omitted; firmware/IP and health sit discreetly in the header, and unknown-parameter fallback is retained (UX-25).
- Active alert monitoring no longer intentionally stops on UI closure/task removal. Reopening reuses one Runtime and retains truth/cooldown state; Android timeout, sign-out and OS limitations still apply. Device acceptance is pending (UPD-03, NTF-03/14, ADR-0010).
- Removed the editable polling/timeout fields from Settings; poll interval and request/command timeouts are fixed release constants (NTF-01).
- Redesigned the custom-alert editor: the list/"New alert" button is shown by default and the creation form only opens on demand; each alert is now exactly one comparison (no AND/OR picker) chosen via a cascaded Location -> Type -> Sensor picker restricted to physical, SI-unit values, with relation and numeric limit completing the alert (NTF-02, NTF-05).
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
