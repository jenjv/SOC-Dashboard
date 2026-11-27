#!/usr/bin/env bash
set -euo pipefail

HOST_NAME="${1:-}"
case "$HOST_NAME" in
    SOC-APPLICATION|SOC-NGINX) ;;
    *) echo "Usage: sudo bash install.sh SOC-APPLICATION|SOC-NGINX" >&2; exit 2 ;;
esac

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

if [[ ! -r /etc/default/fluent-bit ]] || ! grep -q '^SOC_INGEST_TOKEN=.' /etc/default/fluent-bit; then
    echo "SOC_INGEST_TOKEN is missing from /etc/default/fluent-bit." >&2
    exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install -D -o root -g root -m 0755 "$SCRIPT_DIR/heartbeat.py" /usr/local/bin/soc-host-heartbeat.py
install -D -o root -g root -m 0644 "$SCRIPT_DIR/soc-host-heartbeat@.service" /etc/systemd/system/soc-host-heartbeat@.service
install -D -o root -g root -m 0644 "$SCRIPT_DIR/soc-host-heartbeat@.timer" /etc/systemd/system/soc-host-heartbeat@.timer

systemctl daemon-reload
systemctl enable --now "soc-host-heartbeat@${HOST_NAME}.timer"
systemctl start "soc-host-heartbeat@${HOST_NAME}.service"
