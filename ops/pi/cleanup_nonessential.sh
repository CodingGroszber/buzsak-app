#!/usr/bin/env bash
set -euo pipefail

PURGE_HEADSCALE="${1:-no}"

echo "Disabling/removing non-essential services requested by operator"

echo "- headscale.service"
if systemctl list-unit-files | grep -Eq '^headscale\.service[[:space:]]'; then
  sudo systemctl disable --now headscale.service || true
  sudo systemctl mask headscale.service || true
  if [[ "${PURGE_HEADSCALE}" == "purge-headscale" ]]; then
    sudo apt-get purge -y headscale || true
    sudo apt-get autoremove -y || true
  fi
else
  echo "  headscale.service not installed"
fi

if [[ -L /etc/nginx/sites-enabled/headscale ]]; then
  sudo rm -f /etc/nginx/sites-enabled/headscale
  echo "  removed nginx headscale site symlink"
fi

if [[ -L /etc/nginx/sites-enabled/neugarden ]]; then
  sudo rm -f /etc/nginx/sites-enabled/neugarden
  echo "  removed legacy nginx neugarden symlink"
fi

echo "- wg-quick@wg0.service"
sudo systemctl disable --now wg-quick@wg0.service || true
sudo systemctl mask wg-quick@wg0.service || true
sudo systemctl reset-failed wg-quick@wg0.service || true

echo "- Optional stale WireGuard config"
if [[ -f /etc/wireguard/wg0.conf ]]; then
  sudo mv /etc/wireguard/wg0.conf /etc/wireguard/wg0.conf.disabled.$(date +%Y%m%d%H%M%S)
  echo "  moved wg0.conf to disabled backup"
fi

echo "Completed cleanup"
