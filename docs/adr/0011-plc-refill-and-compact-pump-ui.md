# ADR-0011: PLC refill and compact Pump UI

## Status

Accepted feature request from the owner on 2026-10-21. Implementation verified with synthetic UI and loopback command tests; Android and live refill acceptance are pending. No live pump command is authorized by this change.

Covers CTL-01/05/12, UX-25, SSOT-03/08, SRV-16, DATA-02.

## Context

The PLC and server now expose firmware v4.1's refill state machine. The owner requested a Greenhouse-matched Pump layout and a Fill tank action. The server source and adapter contract are authoritative; direct output controls remain unsupported.

## Decision

- Use the existing versioned server command client/Runtime for `refill` with empty params and one UUID4 intent. This is a non-idempotent pulse, not an on/off toggle or a flow measurement. Do not call field-device endpoints.
- Gate on enabled capability with empty schema, healthy/enabled device, online/non-overdue/non-stale server data, fresh AUTO selector code/text, idle refill flags and a valid level below the firmware's 1000 L stop threshold. Unknown, malformed, stale or unavailable prerequisites fail closed. The server remains the final authority.
- On ambiguity lock submission and use GET-only status lookup if an ID is available. No Retry control or automatic replay is introduced. Server status feedback and subsequent physical telemetry remain separate; no optimistic filling state is shown.
- Give Pump the same responsive narrow device column and shared compact ParameterReadout as Greenhouse, grouped into tank/pressure and PLC state. Per the owner's follow-up, omit Sensors/Diagnostics and their known fields from fallback cards while retaining their telemetry for control gating. Put quality-aware firmware/IP in the existing muted header, not a separate Device section. Preserve unknown-parameter fallback and explicit quality states for visible values. Keep pump outputs and physical selector read-only.
- Extend only the loopback fake API for development, including empty-schema capability, synthetic v4.1 telemetry and one-shot refill lifecycle. No server repository or real device is changed.

## Consequences

Older servers remain readable with a disabled Fill tank action. Sensor validity is not proof of calibration; include that caveat, and never infer flow from relay state. PLC firmware owns stop/cancel interlocks. Physical Android and live operation require separate acceptance/owner approval.