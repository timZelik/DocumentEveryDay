#!/usr/bin/env bash
# Mac, nightly: pull today's clips from Photos, pick ~3s of each, label them with one cheap Haiku call,
# render the mosaic, put it back in Photos (so it lands in the iPhone camera roll) and buzz the phone.
# Edit data/days/<date>/day.toml afterwards (stats, labels, skips) and run render-day again if needed.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
DAY="${1:-$(date +%F)}"
.venv/bin/python -m documenteveryday make-day --date "$DAY" --collect --auto-label --to-photos
if [[ -n "${DOCUMENTEVERYDAY_NTFY_TOPIC:-}" ]]; then
  curl -s -H "Title: Day video ready" -d "Your $DAY mosaic is in Photos > DocumentEveryDay." \
    "${DOCUMENTEVERYDAY_NTFY_SERVER:-https://ntfy.sh}/$DOCUMENTEVERYDAY_NTFY_TOPIC" >/dev/null
fi
