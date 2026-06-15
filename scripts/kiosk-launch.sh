#!/usr/bin/env bash
# Mac dry-run: open Chrome in app mode pointing at the local dashboard.
# Useful for verifying the layout looks right at a given resolution before
# deploying to the Pi.
set -euo pipefail

URL="${1:-http://localhost:8000}"
PROFILE="${HOME}/.chrome-kiosk-profile"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME" ]; then
  echo "Google Chrome not found at $CHROME" >&2
  exit 1
fi

"$CHROME" \
  --user-data-dir="$PROFILE" \
  --app="$URL" \
  --start-fullscreen \
  --noerrdialogs \
  --disable-infobars \
  --disable-pinch \
  --overscroll-history-navigation=0
