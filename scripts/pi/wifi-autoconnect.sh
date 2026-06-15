#!/usr/bin/env bash
# Actively brings up Wi-Fi and waits for it, instead of trusting
# network-online.target: on a Pi, NetworkManager-wait-online can report
# "online" before the brcmfmac Wi-Fi firmware has finished initializing
# (firmware load + power-mgmt setup takes ~30-40s, which can lose the race
# with NetworkManager's own startup-complete check). Retried via a oneshot
# boot gate and a periodic timer (see wifi-autoconnect.service/.timer).
set -uo pipefail

TIMEOUT_S="${1:-90}"
INTERVAL_S=3
elapsed=0

is_connected() {
  nmcli -t -f GENERAL.STATE device show wlan0 2>/dev/null | grep -q "^GENERAL.STATE:100 (connected)"
}

wifi_profile() {
  nmcli -t -f NAME,TYPE,AUTOCONNECT connection show 2>/dev/null \
    | awk -F: '$2=="802-11-wireless" && $3=="yes" {print $1; exit}'
}

while ! is_connected && [ "$elapsed" -lt "$TIMEOUT_S" ]; do
  profile="$(wifi_profile)"
  if [ -n "$profile" ]; then
    nmcli connection up "$profile" >/dev/null 2>&1 || true
  fi
  sleep "$INTERVAL_S"
  elapsed=$((elapsed + INTERVAL_S))
done

is_connected
