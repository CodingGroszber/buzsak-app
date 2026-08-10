#!/usr/bin/env bash
set -euo pipefail

PROJECT_PATH="${1:-/home/neulas/projects/py_app}"
DEPLOY_MODE="${2:-full}"
SERVICE_NAME="py-app-dashboard.service"

echo "[1/8] Validating project path: ${PROJECT_PATH}"
if [[ ! -d "${PROJECT_PATH}" ]]; then
  echo "Project path does not exist: ${PROJECT_PATH}" >&2
  exit 1
fi

cd "${PROJECT_PATH}"

if [[ "${DEPLOY_MODE}" == "quick" ]]; then
  echo "[2/8] Quick mode: skipping apt package refresh"
else
  echo "[2/8] Installing minimal runtime packages"
  sudo apt-get update -y
  sudo apt-get install -y python3-venv python3-pip nginx tailscale
fi

echo "[3/8] Creating/updating venv"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
if [[ "${DEPLOY_MODE}" == "quick" ]]; then
  echo "Quick mode: refreshing app package only"
  pip install --no-deps .
else
  pip install --upgrade --force-reinstall \
    "flet==0.28.3" \
    "flet-web==0.28.3" \
    "flet-cli==0.28.3"
  pip uninstall -y flet-desktop || true
  pip install .
fi

echo "[4/8] Installing systemd service from repo"
sudo cp "${PROJECT_PATH}/ops/pi/systemd/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[5/8] Installing nginx site from repo"
sudo cp "${PROJECT_PATH}/ops/pi/nginx/py-app-dashboard.conf" /etc/nginx/sites-available/py-app-dashboard.conf
sudo ln -sfn /etc/nginx/sites-available/py-app-dashboard.conf /etc/nginx/sites-enabled/py-app-dashboard.conf

if [[ -f /etc/nginx/sites-enabled/default ]]; then
  sudo rm -f /etc/nginx/sites-enabled/default
fi
if [[ -f /etc/nginx/sites-enabled/headscale ]]; then
  sudo rm -f /etc/nginx/sites-enabled/headscale
fi

sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx

echo "[6/8] Verifying dashboard and proxy"
curl -sS -I http://127.0.0.1:8550 | head -n 1 || true
curl -sS -I http://127.0.0.1 | head -n 1 || true

echo "[7/8] Service summary"
sudo systemctl --no-pager --full status "${SERVICE_NAME}" | sed -n '1,20p'
sudo systemctl --no-pager --full status nginx | sed -n '1,20p'

echo "[8/8] Completed"
