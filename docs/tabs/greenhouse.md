# Greenhouse Tab

Covers VLV-01..VLV-09, CTL-01..CTL-10, UX-01..UX-02.

## Content

- Device health and identity details, Sensor A/B readings and diagnostics.
- Current mode and four relay states: Mist, Rain, Drip and Light.
- Mist/rain automation summaries, schedule and progress; automation is visibly frozen in Manual mode.

## Controls and gating

- Manual/Automatic submits on the explicit segment tap. The inline warning explains that a mode change closes all valves; displayed mode remains server-reported.
- Relay controls require enabled server capability, healthy device, fresh good relay/mode/controllability metadata, and the configured `always_manual` exception. The server remains the authority.
- A command is submitted once with its idempotency key. Ambiguous outcomes are locked pending an explicit status check or supported same-intent retry; no physical state changes optimistically.

## Edge cases

- Disabled capabilities show the server's `disabled_reason`.
- Stale, invalid or unavailable gating data disables the affected control.
- Unknown capability/action schema does not enable a control.
