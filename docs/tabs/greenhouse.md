# Greenhouse Tab

Covers VLV-01..VLV-11, CTL-01..CTL-10, UX-01..UX-02, UX-26..UX-28, SRV-17.

## Content

- The same compact header as Pump: muted quality-aware firmware/IP beside health, with no raw device-name heading. Identity-only changes refresh the header in place.
- Sensors precede Automation. Each healthy sensor is one unframed row: status icon and Sensor A/B at left, compact temperature / humidity at right (for example `21.6°C / 87.4%`). Faults and non-good measurement quality retain explicit badges/error text and distinct accessible status icons; zero is never rendered as missing. Routine sample age and value timestamps are in the row tooltip, not extra helper lines. Firmware/IP do not repeat after the sensors.
- Current mode and four relay states: Mist, Rain, Drip and Light.
- Daily Rain schedule after the valve controls, visible only in fresh server-reported Manual mode: HH:MM start, whole minutes (1..60), and Apply in one compact row. Automatic/unknown/stale mode hides the entire editor without discarding drafts. Tighter section gaps and panel padding match the controller page's density; the shared header and bounded scrolling remain unchanged.
- Mist/rain automation follows the sensor rows, with mist target/duty paired horizontally, schedule and progress retained; automation remains visibly frozen in Manual mode.

## Controls and gating

- Manual/Automatic submits on the explicit segment tap. The inline warning explains that a mode change closes all valves; displayed mode remains server-reported.
- Relay controls require enabled server capability, healthy device, fresh good relay/mode/controllability metadata, and the configured `always_manual` exception. The server remains the authority.
- A command is submitted once with its idempotency key. Ambiguous outcomes are locked pending an explicit status check or supported same-intent retry; no physical state changes optimistically.

## Rain Schedule

Read-only inspection of `http://192.168.1.109/` on 2026-10-21 verified daily start/duration/Apply on the controller page. Its firmware permits edits in either mode; the app follows the stricter authoritative server DEV-12 contract instead. No device POST was sent.

Apply uses the existing server command client and shared Greenhouse busy/uncertainty lock, with `set_rain_schedule` and `{start: "HH:MM", duration_minutes: int}`. The capability must advertise the exact schema and be enabled; the deployment needs both valve and separate rain-schedule gates (the latter defaults false). Show the server's disabled reason rather than bypassing it.

Require fresh healthy/enabled controller data, online/non-overdue server state, manual mode, idle `rain_valve_on` and `relay2_rain`, and a valid current reported schedule. Local mode/relay/schedule intents cannot overlap. The server checks its queue, revisions and physical prerequisites again before transmission; a rejected server precondition does not trigger a retry or mode switch.

The form is a draft; polling and mode changes do not discard unsaved changes. Existing rain readouts continue to show server values, even after HTTP acceptance or a command receipt. A qualifying confirmed write uses fresh post-attempt hour/minute/duration-seconds telemetry. Apply progress/result, validation errors and disabled reasons are inline when relevant, with no empty feedback rows or visible explanatory helper paragraph. The required valve-closing warning stays as a single short line.

Use Europe/Budapest controller-local time, including DST; midnight-crossing windows are allowed. Returning to Automatic or rebooting within the configured window may start watering. Runtime readback does not prove NVS/reboot durability, physical valve movement or water flow. These schedule caveats are in the Apply tooltip and this documentation, not a visible helper paragraph; the start tooltip identifies HH:MM/controller time. No app-side timer, Pi scheduler, day-of-week recurrence, enable toggle or automatic mode change is invented.

An ambiguous write locks conflicting controls and is never resent. If the command ID is known, Check status is GET-only; an unrelated previous command ID is never reused. A separate explicit Apply after a definitive result uses a new UUID. Old servers remain usable with the editor disabled. Synthetic/loopback verification is implemented; Android and live operation need separate acceptance and owner approval.

## Edge cases

- Disabled capabilities show the server's `disabled_reason`.
- Stale, invalid or unavailable gating data disables the affected control.
- Unknown capability/action schema does not enable a control.
- Device content shrink-wraps inside the scroll viewport; empty generic grids are hidden. The page ends after the last visible automation reading with normal padding, not a wrapping/expanding firmware footer or trailing empty section (UX-26).
