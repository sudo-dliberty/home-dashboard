#!/usr/bin/env bash
# Wait for the backend to be reachable, then launch Chromium in kiosk mode.
# Called by LXDE autostart on Pi boot.
set -euo pipefail

URL="${DASHBOARD_URL:-http://127.0.0.1:8000}"
PROFILE="${HOME}/.config/chromium-kiosk"

# Wait up to 60s for the backend
for i in $(seq 1 60); do
  if curl -sf --max-time 1 "${URL}/api/health" >/dev/null; then
    break
  fi
  sleep 1
done

# Disable display sleep & screensaver (xset is provided by x11-xserver-utils)
xset -dpms s noblank s off 2>/dev/null || true
# Hide the mouse cursor after 0.1s of idle (unclutter must be installed).
# X11 only — under labwc/Wayland (current Raspberry Pi OS) the window rule in
# scripts/pi/labwc-rc.xml hides the cursor instead.
unclutter -idle 0.1 -root &

exec chromium \
  --ozone-platform=wayland \
  --password-store=basic \
  --user-data-dir="$PROFILE" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  --autoplay-policy=no-user-gesture-required \
  --start-fullscreen \
  "$URL"
