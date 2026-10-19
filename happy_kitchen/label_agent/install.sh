#!/bin/bash
# Installs the Happy Kitchen label agent on a Raspberry Pi (Raspberry Pi OS / Debian).
# Run from this folder:   sudo bash install.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run with sudo: sudo bash install.sh"; exit 1; }
cd "$(dirname "$0")"

id hk-label >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin hk-label
usermod -aG lp hk-label

install -d -m 755 /opt/hk-label-agent
install -m 755 hk_label_agent.py /opt/hk-label-agent/hk_label_agent.py

if [ ! -f /etc/hk-label-agent.conf ]; then
  cat > /etc/hk-label-agent.conf <<'CONF'
[erp]
# hcl-erp.fbs-host.com until go-live, then erp.fbs-host.com
url = https://hcl-erp.fbs-host.com
# From the ERP: User "label printer" > Settings > API Access > Generate Keys.
api_key =
api_secret =
# Exactly as the Label Printer is named in the ERP
printer = Kitchen Zebra

[output]
# Zebra / ZPL printer on USB: leave device as it is.
device = /dev/usb/lp0
# Any other printer set up in CUPS: empty the device line and name the CUPS queue here.
cups_queue =
poll_seconds = 3
CONF
  echo "Created /etc/hk-label-agent.conf. Fill in api_key and api_secret: sudo nano /etc/hk-label-agent.conf"
fi
chown root:hk-label /etc/hk-label-agent.conf
chmod 640 /etc/hk-label-agent.conf

cat > /etc/systemd/system/hk-label-agent.service <<'UNIT'
[Unit]
Description=Happy Kitchen label agent
After=network-online.target
Wants=network-online.target

[Service]
User=hk-label
Group=lp
ExecStart=/usr/bin/python3 /opt/hk-label-agent/hk_label_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable hk-label-agent >/dev/null
if grep -qE '^api_key = .+' /etc/hk-label-agent.conf; then
  systemctl restart hk-label-agent
  echo "Agent started. Watch it: journalctl -u hk-label-agent -f"
else
  echo "Agent installed but not started yet: add the API key, then run: sudo systemctl restart hk-label-agent"
fi
