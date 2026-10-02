#!/usr/bin/env bash
# Daily restart of the kiosk Chromium to prevent long-uptime memory accumulation.
# Intended to be run from a user cron job overnight (e.g. after the monitor is
# turned off). Safe to run anytime; relaunches under a transient systemd --user
# unit so it survives the invocation that started it.
set -uo pipefail

PROFILE="${HOME}/.config/chromium-kiosk"
URL="${DASHBOARD_URL:-http://127.0.0.1:8000}"

systemctl --user reset-failed chromium-kiosk.service 2>/dev/null || true
systemctl --user stop chromium-kiosk.service 2>/dev/null || true
pkill -f "$PROFILE" 2>/dev/null || true
sleep 3

# Don't relaunch until the backend answers (e.g. right after a deploy restarts
# it): a failed first load leaves Chromium on an error page or a cached copy.
for _ in $(seq 1 60); do
  curl -sf --max-time 1 "${URL}/api/health" >/dev/null && break
  sleep 1
done

systemd-run --user \
  --unit=chromium-kiosk \
  --setenv=WAYLAND_DISPLAY=wayland-0 \
  --setenv=XDG_RUNTIME_DIR="/run/user/$(id -u)" \
  /usr/bin/chromium \
    --ozone-platform=wayland \
    --password-store=basic \
    --user-data-dir="$PROFILE" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --check-for-update-interval=31536000 \
    "$URL"
