# Pump Tab

Covers UX-01..UX-02, UX-25..UX-26, DATA-02, SSOT-07..SSOT-08, CTL-12, SRV-16.

## Content

- Server-driven PUMP party and device sections, ordered as received.
- Greenhouse-matched responsive device column, device health/header, section headings, compact label/value rows, quality badges and detailed timestamp tooltips. Greenhouse and Pump use the same ParameterReadout component.
- Fill tank at the top, followed only by tank/pressure and PLC state (selector, request/active fill, pump outputs).
- Sensors and Diagnostics are intentionally omitted, including their known raw-input, signal, indicator, controllability and legacy-contact fields; they do not reappear as generic cards. Their telemetry remains available to the safety gates. Unknown parameter ids retain generic KPI-card fallback.
- The `garden-plc` device-name heading is omitted; firmware/IP and health remain in the same discreet header row used by Greenhouse. Identity includes quality text when stale/invalid/unavailable and updates in place even when device health is unchanged. There is no separate Device section; the underlying device ID and command routing are unchanged.

## Controls and gating

- Pump and indicator outputs remain read-only. The app never calls the PLC directly, exposes `set_output`, or edits the physical selector.
- **Fill tank** sends one `refill` intent with empty params through the authenticated server command API. Capability must be enabled with an empty schema; device healthy/enabled; server online, non-overdue and non-stale; selector fresh AUTO (text plus integer code 1); refill flags false; water-level signal true; finite numeric tank level below 1000 L and not negative.
- Deployment-disabled capability displays the server's reason. Busy requests disable the button immediately. Accepted/confirmed command status never changes physical readouts; later snapshots own them.
- Refill is non-idempotent: no retry button and no automatic/manual retransmission after ambiguity. An uncertain result locks the action; if a command ID is available, **Check status** uses GET only. Without an ID, inspect the system rather than resend. Definitive status lookup resolves the uncertainty lock; all telemetry gates still apply.
- A confirmed request means the server observed a post-attempt refill pulse/active state, not that the tank is full. PLC interlocks own filling/cancellation. Relay state does not prove water flow, and sensor calibration is not independently verified.
- Unknown parameter ids use the generic presentation fallback; missing or invalid values are not coerced to zero/off.

## Edge cases

- Unconfigured parties and devices without data use explicit explanatory or quality states.
- Stale telemetry remains visible as stale and is not treated as a current physical state.
- Synthetic unit and loopback HTTP tests cover enablement, invalid/missing/stale states, double taps, uncertain outcomes, GET-only lookup, offline/overdue recovery, same-control updates and unknown fields. No live refill actuation is approved or performed. Android verification remains pending.
