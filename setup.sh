#!/bin/bash
# Setlist CMDR — Raspberry Pi Setup Script
# Run once as your normal user (not root):  bash setup.sh

set -e
echo ""
echo "═══════════════════════════════════════"
echo "  Setlist CMDR — Pi Setup"
echo "═══════════════════════════════════════"
echo ""

# 1. System packages
echo "► Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-venv -qq

# 2. Python virtual environment
echo "► Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate

# 3. Systemd service for auto-start
echo "► Installing systemd service..."
SERVICE_DIR=$(pwd)
cat > /tmp/setlist-cmdr.service << EOF
[Unit]
Description=Setlist CMDR Server
After=network.target

[Service]
User=$USER
WorkingDirectory=$SERVICE_DIR
ExecStart=$SERVICE_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/setlist-cmdr.service /etc/systemd/system/setlist-cmdr.service
sudo systemctl daemon-reload
sudo systemctl enable setlist-cmdr.service
sudo systemctl start setlist-cmdr.service

echo ""
echo "✓ Setlist CMDR is running!"
echo ""
echo "  Leader view  →  http://$(hostname -I | awk '{print $1}'):8000/leader"
echo "  Musician URL →  http://$(hostname -I | awk '{print $1}'):8000/"
echo ""

