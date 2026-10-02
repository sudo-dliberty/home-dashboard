#!/usr/bin/env bash
# Idempotent Pi installer for the Astoria Home Dashboard.
# Run as the pi user (NOT root). Re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

require_apt() {
  local missing=()
  for pkg in "$@"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "==> apt install: ${missing[*]}"
    sudo apt-get update
    sudo apt-get install -y "${missing[@]}"
  fi
}

echo "==> Verifying live monitor resolution"
xrandr | grep -E "(connected|\*)" || echo "(xrandr not available — confirm display manually)"

require_apt \
  python3 python3-venv python3-pip \
  nodejs npm \
  chromium \
  unclutter \
  x11-xserver-utils \
  curl

echo "==> Building backend venv"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> Building frontend"
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install
fi
npm run build

echo "==> Installing Wi-Fi reliability units (boot-time autoconnect gate + periodic watchdog)"
chmod +x "$ROOT/scripts/pi/wifi-autoconnect.sh"
sudo cp "$ROOT/scripts/pi/wifi-autoconnect.service" /etc/systemd/system/
sudo cp "$ROOT/scripts/pi/wifi-watchdog.service" /etc/systemd/system/
sudo cp "$ROOT/scripts/pi/wifi-watchdog.timer" /etc/systemd/system/
sudo cp "$ROOT/scripts/pi/wifi-powersave-off.conf" /etc/NetworkManager/conf.d/
sudo systemctl daemon-reload
sudo systemctl enable --now wifi-autoconnect.service wifi-watchdog.timer
sudo systemctl try-restart NetworkManager

echo "==> Installing systemd unit"
sudo cp "$ROOT/scripts/pi/home-dashboard.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now home-dashboard.service

echo "==> Installing labwc config (hides the cursor over the kiosk)"
mkdir -p "$HOME/.config/labwc"
LABWC_RC="$HOME/.config/labwc/rc.xml"
if [ ! -f "$LABWC_RC" ] || cmp -s "$ROOT/scripts/pi/labwc-rc.xml" "$LABWC_RC"; then
  cp "$ROOT/scripts/pi/labwc-rc.xml" "$LABWC_RC"
  labwc --reconfigure 2>/dev/null || true
else
  echo "    $LABWC_RC already exists with other settings — not overwriting."
  echo "    Merge the <windowRules> from scripts/pi/labwc-rc.xml into it by hand."
fi

echo "==> Installing LXDE autostart entry"
mkdir -p "$HOME/.config/autostart"
cp "$ROOT/scripts/pi/kiosk.desktop" "$HOME/.config/autostart/"
chmod +x "$ROOT/scripts/pi/kiosk-start.sh"

echo
echo "==> Done."
echo "Backend status:  sudo systemctl status home-dashboard.service"
echo "Backend logs:    journalctl -u home-dashboard.service -f"
echo "Open in Chromium now:  $ROOT/scripts/pi/kiosk-start.sh"
echo "On next reboot, the kiosk will autostart."
echo
echo "Set PHOTO_DIR in $ROOT/.env (copy from .env.example) so photos appear."
