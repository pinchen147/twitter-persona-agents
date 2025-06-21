#!/bin/bash
# Install Twitter Persona Agents as a systemd service for 24/7 operation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="twitter-persona-agents"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "🚀 Installing Twitter Persona Agents as systemd service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run as root (use sudo)"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create systemd service file
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Twitter Persona Agents - Multi-Account Twitter Bot
Requires=docker.service
After=docker.service
StartLimitIntervalSec=0

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.prod.yml down
ExecReload=/usr/bin/docker-compose -f docker-compose.prod.yml restart
TimeoutStartSec=300
TimeoutStopSec=120

# Restart configuration
Restart=on-failure
RestartSec=10
StartLimitBurst=3

# Security settings
User=root
Group=docker

# Environment
Environment=COMPOSE_PROJECT_NAME=twitter-persona-agents-prod

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=twitter-persona-agents

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Created systemd service file: $SERVICE_FILE"

# Reload systemd
systemctl daemon-reload
echo "✅ Reloaded systemd daemon"

# Enable service to start on boot
systemctl enable "$SERVICE_NAME"
echo "✅ Enabled $SERVICE_NAME to start on boot"

echo ""
echo "🎉 Installation complete! Service commands:"
echo ""
echo "Start service:    sudo systemctl start $SERVICE_NAME"
echo "Stop service:     sudo systemctl stop $SERVICE_NAME"
echo "Restart service:  sudo systemctl restart $SERVICE_NAME"
echo "Service status:   sudo systemctl status $SERVICE_NAME"
echo "View logs:        sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "The service will automatically start on system boot."
echo ""
echo "⚠️  Before starting, ensure:"
echo "1. .env file is configured with API keys"
echo "2. config/config.yaml is properly set up"
echo "3. Source material PDFs are in data/source_material/"
echo "4. Knowledge base is built: python -m ingest.split_embed"