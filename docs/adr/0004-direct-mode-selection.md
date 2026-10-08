# ADR-0004: Submit mode changes directly from the segmented control

- **Status:** Accepted (owner request, 2026-10-08)
- **Covers:** VLV-03, CTL-05, SSOT-06
- **Supersedes:** The modal-confirmation portion of VLV-03 / prior implementation

## Context

The valve-controller firmware closes all valves on a mode change. The prior app required a popup confirmation after a Manual/Automatic tap. The owner requested that a segment tap execute the action directly.

## Decision

- A tap on Manual or Automatic submits `set_mode` immediately; there is no confirmation popup.
- A persistent inline hint warns that changing mode closes all valves.
- The segmented selection remains at the last server-reported mode while the command is pending. The app does not optimistically show a new physical mode.
- Relay gates continue to require fresh server-reported mode, capability, health and output metadata. The Pi remains the only path to the ESP32.

## Consequences

- One segment tap is the explicit user intent to change mode; the inline warning is visible before the tap.
- Mode changes still close all valves as a device-side effect. A confirmed app state is based on server telemetry, not HTTP acceptance.
