#!/usr/bin/env bash
# Serves DocumentEveryday on this Mac and keeps it awake while it runs.
# Reach it from the iPhone through `tailscale serve --bg 8000` (see README).
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  echo "Missing .env: cp .env.example .env and fill it in." >&2
  exit 1
fi
set -a
source .env
set +a
# caffeinate -i: no idle sleep while serving; -s: no system sleep on AC power. Closing a MacBook lid still
# sleeps it (unless an external display is attached), so leave the lid open while a batch runs.
exec caffeinate -is .venv/bin/python -m documenteveryday serve --host 127.0.0.1 --port 8000
