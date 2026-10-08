# ADR-0005: Expose Garage pulse controls in release 1.0

- **Status:** Accepted (owner approval, 2026-10-08)
- **Covers:** CTL-02, CTL-05, CTL-11, SSOT-06

## Context

The server already exposes an operator-authenticated, server-controlled Sonoff pulse and reports its lifecycle through `last_pulse`. The original release scope treated all Garage controls as read-only. The owner first approved Garage Left (`sonoff-2`) and later requested the same in-app control for Garage Right (`sonoff-1`).

## Decision

- The app exposes one compact Trigger row for each Garage device.
- Each button is enabled only when that device's pulse capability is enabled, health is healthy, and fresh good `on_off` telemetry exists.
- The app sends one POST and never resubmits a pulse, including after an ambiguous result. A status check is GET-only.
- HTTP 202 means accepted. Completion is displayed only from a later server-reported `last_pulse` state.
- The button describes relay and pulse state only. It does not claim the garage door is open or closed.

## Consequences

- The server remains the sole path to the Sonoff and the source of reported state.
- Garage Left has been verified live once through the API and the owner confirmed the app action works. No Garage Right pulse has been sent in live verification. Fake-server tests never contact hardware.
