#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="py-app-dashboard.service"

echo "=== HOST ==="
hostnamectl | sed -n '1,12p'

echo ""
echo "=== DASHBOARD SERVICE ==="
sudo systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,30p'

echo ""
echo "=== NGINX ==="
sudo systemctl --no-pager --full status nginx | sed -n '1,20p'

echo ""
echo "=== TAILSCALE ==="
sudo systemctl --no-pager --full status tailscaled.service | sed -n '1,20p'

echo ""
echo "=== PORTS ==="
sudo ss -ltnp | egrep ':(80|443|8550|5580)\b' || true

echo ""
echo "=== LOCAL HTTP PROBES ==="
curl -sS -I http://127.0.0.1:8550 | head -n 1 || true
curl -sS -I http://127.0.0.1 | head -n 1 || true

echo ""
echo "=== FAILED UNITS ==="
systemctl --failed --no-pager || true

echo ""
echo "=== TAILSCALE STATUS ==="
tailscale status || true
