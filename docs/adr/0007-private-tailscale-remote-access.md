# ADR-0007: Private Tailscale route for post-1.0 remote access

- **Status:** Accepted requirements decision; implementation deferred post-1.0 (owner decisions, 2026-10-08)
- **Covers:** SEC-02, SEC-07, ENV-05, ENV-06, SRV-15, AT-09, B-405

## Context

The app currently reaches the Pi only on the home LAN at `https://192.168.1.95`. It validates that endpoint using the existing pinned Caddy CA and authenticates API requests with server-issued bearer tokens. The owner wants the same app behavior while away from the LAN and selected Tailscale. This decision does not authorize changes to the separate server repository or live hardware tests.

## Decisions

- Remote connectivity is private to the owner's Tailscale tailnet. No Tailscale Funnel, public port forwarding, or public endpoint is in scope.
- The official Tailscale Android app supplies the phone's VPN connection. The Buzsák app does not embed a Tailscale SDK or manage VPN state; without the VPN it uses its ordinary offline/recovery behavior.
- The Raspberry Pi is the subnet-route provider and advertises only `192.168.1.95/32`. The route must be approved in the tailnet policy. All tailnet members may reach this host route; API access still requires a valid bearer token and server role.
- Detailed Pi-side requirements are maintained separately in [tailscale-remote-access-requirements.md](../tailscale-remote-access-requirements.md); this app repository does not change the server project.
- The app keeps `https://192.168.1.95` and the existing pinned Caddy CA. TLS verification, authentication, capability gates and control behavior are unchanged.
- Remote access is a post-1.0 milestone. Pi Tailscale setup and route testing are prerequisites, owned outside this app repository.

## Consequences

- No app transport or API endpoint change is required if the route works as specified.
- A phone on the home LAN continues to use the same address; off-LAN access requires Tailscale connected.
- Acceptance verifies authenticated telemetry over the route from a physical phone, disconnected-VPN offline behavior and absence of public exposure. It does not actuate hardware.
- Server-side installation and route approval must be coordinated with the server owner; this repository does not change the server project.
