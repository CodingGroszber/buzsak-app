# ADR-0012: Controller-owned daily rain schedule

## Status

Accepted feature request and compact-layout follow-up from the owner on 2026-10-21. The full Python suite passes 545 tests, including synthetic control and loopback integration checks. The updated APK built successfully on 2026-10-21 (133.5 MB). The initial editor was checked at desktop/phone widths; the revised compact form has structural/visibility coverage, with final visual and Android/live acceptance still pending. No real schedule write or deployment is authorized by this change.

Covers VLV-11, UX-27, SRV-17, CTL-01/05, SSOT-03/08, DATA-02.

## Context

The updated server exposes the valve firmware's existing daily rain schedule. A read-only inspection of the controller page confirmed start time, minute duration and Apply controls. Server DEV-12 and its adapter/catalog, capability query, command service and dispatcher define the consumed contract; the firmware page is a visual reference, not an app transport endpoint.

## Decision

- Add a densely packed schedule editor between valves and automation, visible only for server-reported fresh Manual mode, retaining the uniform header, sensor panels and bounded scrolling. Use one row for HH:MM, numeric 1..60 minutes and Apply. Per the owner's follow-up, remove visible helper prose and empty feedback space; keep actionable errors/status, server disabled reasons and the required short mode-change warning. Drafts survive visibility/mode changes.
- Use `set_rain_schedule` through the existing versioned server command API, shared Greenhouse command owner and UUID intent. Validate the exact supported advertised schema and strict numeric/time bounds. Independent server gate, fresh healthy manual mode, idle rain signals and valid current readback are required; the server independently enforces queue/revision checks before transmission.
- Draft inputs and reported schedule are separate. Preserve unsaved drafts through polls. Only server telemetry updates displayed runtime configuration; neither HTTP acceptance nor edited fields imply a physical-state change.
- Honor `retry_safe=false`: no automatic/manual resend after ambiguity, and no same-key Retry button for this action. Lock conflicting controller intents; GET-only status lookup is permitted only for the current known command ID. Separate explicit Apply after a definitive outcome uses a fresh UUID. Existing supported mode/output retry behavior is not broadened.
- The controller owns Europe/Budapest daily timing, DST and midnight-crossing windows. Do not add a Python/Pi scheduler, automatic mode changes, day-of-week rules or a speculative enable flag.

## Consequences

Both valve and rain-schedule deployment gates must be enabled by the server owner; the new gate defaults false. A schedule can lead to watering on a later Automatic-mode return or reboot during its window. Per the owner's compact-layout follow-up, this caveat remains in the Apply tooltip and documentation instead of a visible helper paragraph; timezone is also in the start-field tooltip. Confirmed telemetry proves runtime configuration only, not NVS/reboot durability or flow. Older servers stay readable with disabled scheduling in Manual mode.

All command tests use synthetic data or the loopback fake API. Device operations and production gate/deployment changes still need explicit owner approval.