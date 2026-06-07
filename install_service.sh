#!/usr/bin/env bash
set -e
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/arrow.service"

if [[ "$EUID" -ne 0 ]]; then
  echo "Please run this script as root: sudo ./install_service.sh"
  exit 1
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Arrow AI Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
ExecStart=/bin/bash $REPO_DIR/run_arrow.sh
Restart=always
RestartSec=5
StandardOutput=append:$REPO_DIR/arrow_data/logs/arrow.log
StandardError=append:$REPO_DIR/arrow_data/logs/arrow.err
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable arrow.service
systemctl start arrow.service

echo "Arrow systemd service installed and started."
