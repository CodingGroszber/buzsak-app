#!/usr/bin/env bash
set -euo pipefail

SSH_TARGET="${1:-rpi3}"
PROJECT_PATH="${2:-/home/neulas/projects/py_app}"

# Fast path: no cleanup, no apt refresh, app/service restart + verification.
python ops/pi/deploy.py \
  --ssh-target "${SSH_TARGET}" \
  --project-path "${PROJECT_PATH}" \
  --quick
