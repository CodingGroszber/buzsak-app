# Pump Tab

Covers UX-01..UX-02, DATA-02, SSOT-07..SSOT-08.

## Content

- Server-driven PUMP party and device sections, ordered as received.
- Device health and all reported parameters as KPI cards, including labels, units, quality, freshness and details where available.

## Controls and gating

- PUMP is read-only in release 1.0. The app does not call the PLC or expose `garden_plc.set_output` controls.
- Unknown parameter ids use the generic presentation fallback; missing or invalid values are not coerced to zero/off.

## Edge cases

- Unconfigured parties and devices without data use explicit explanatory or quality states.
- Stale telemetry remains visible as stale and is not treated as a current physical state.
