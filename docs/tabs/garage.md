# Garage Tab

Covers CTL-02, CTL-05, CTL-11, UX-01..UX-02, UX-23.

## Content

- One compact daily-use row per server Sonoff: Garage Right (`sonoff-1`) and Garage Left (`sonoff-2`).
- Each row shows the friendly device name, an explicit relay on/off or unavailable state, and a Trigger button.

## Controls and gating

- Trigger requires that device's pulse capability to be enabled, device health to be healthy, and `on_off` to be fresh and good.
- The app sends exactly one pulse POST. It never retries a pulse, including after an ambiguous response; status recovery is GET-only and uses the server's `last_pulse` snapshot.
- Acceptance is not completion. Pending, sent, succeeded, failed, expired and uncertain states are rendered inline.

## Edge cases

- Missing, stale, invalid or unavailable relay telemetry disables Trigger.
- `on_off` reports relay state only; the UI never infers whether the door is open or closed.
- Garage Right has in-app control but has not been live-actuated in acceptance testing. Tests use only the loopback fake server.
