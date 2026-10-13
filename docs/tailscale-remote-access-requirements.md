# Tailscale Remote Access Requirements

| Field | Value |
|---|---|
| Status | Approved requirements; post-1.0 implementation not started |
| Owner decision date | 2026-10-08 |
| Related | `requirements.md` SEC-07, ENV-06, SRV-15, AT-09; ADR-0007; backlog B-405 |
| Scope | Pi network configuration and remote acceptance; this file does not authorize edits to the server repository or real hardware commands |

## Verified facts

- The app currently calls `https://192.168.1.95` and verifies the server with its pinned Caddy root CA.
- The API requires a bearer token; command endpoints require an appropriate server role.
- The current app has no Tailscale SDK or VPN-management feature.

## Accepted owner decisions

- Remote access is private to the Tailscale tailnet. Do not use Tailscale Funnel, public port forwarding, or another public endpoint.
- The Android device runs the official Tailscale app/VPN. Buzsak uses the existing HTTPS API URL and does not manage VPN connection state.
- The Raspberry Pi is the route provider and advertises only `192.168.1.95/32`.
- All members of the private tailnet may reach this host route. Server bearer-token roles remain required for API access.
- Remote app behavior is the same as on the LAN, including existing freshness, capability and command gates. This decision does not grant additional live-actuation approval.
- The work is post-1.0.

## Pi-side requirements

| ID | Requirement |
|---|---|
| TAIL-PI-01 | The Pi MUST join the owner's private Tailscale tailnet and restore the service after reboot. |
| TAIL-PI-02 | The Pi MUST advertise only the host route `192.168.1.95/32`; the route MUST be approved in the tailnet policy. It MUST NOT advertise the full home subnet or act as an exit node for this feature. |
| TAIL-PI-03 | The Pi MUST NOT expose the Buzsák API through Funnel, public DNS, public port forwarding or a public firewall rule. |
| TAIL-PI-04 | The existing Caddy HTTPS listener, `https://192.168.1.95` URL and pinned root CA MUST remain valid and unchanged. Requests arriving over Tailscale MUST reach the same API and retain bearer authentication and viewer/operator role checks. |
| TAIL-PI-05 | The configured tailnet access policy MUST allow all tailnet members to reach this host route, as approved by the owner; server authentication and roles remain independently enforced. |
| TAIL-PI-06 | Before enabling remote use, verify from an authorized physical phone outside the home LAN that the official Tailscale VPN can reach the existing HTTPS URL and retrieve an authenticated state snapshot. Disconnecting Tailscale MUST produce the app's existing offline state; reconnecting MUST recover without a restart. |
| TAIL-PI-07 | Network acceptance MUST NOT send valve or garage commands. Any later live actuation test remains subject to separate explicit owner approval and the existing safety requirements. |

## Implementation notes and open deployment checks

These are implementation checks, not new architecture decisions: confirm the Pi's Tailscale version/service management, Linux forwarding and firewall behavior for a host route terminating on the Pi itself, tailnet route approval, and the phone's cellular test conditions. The route must be proven before marking B-405 done.

Pi configuration belongs in the server/deployment workstream. This app repository records the dependency but does not modify the server repository.
