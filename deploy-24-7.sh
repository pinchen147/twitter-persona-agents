#!/bin/bash
# Quick deployment script for 24/7 Twitter Persona Agents

set -e

echo "🧘 Deploying Twitter Persona Agents for 24/7 operation..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "   Copy config/secrets.env.example to .env and add your API keys"
    exit 1
fi

# Check if config exists
if [ ! -f config/config.yaml ]; then
    echo "❌ config/config.yaml not found!"
    echo "   Copy config/config.example.yaml to config/config.yaml"
    exit 1
fi

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data/{chroma,logs,backups,source_material}
mkdir -p logs

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Build and start in production mode
echo "🔨 Building production containers..."
docker-compose -f docker-compose.prod.yml build

echo "🚀 Starting services in production mode..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check if containers are running
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    echo "✅ Services started successfully!"
    echo ""
    echo "🎛️  Control Panel: http://localhost:8582"
    echo "🔍 Health Check:  http://localhost:8582/health"
    echo "📊 Deep Health:   http://localhost:8582/health/deep"
    echo ""
    echo "📋 Management commands:"
    echo "View logs:        docker-compose -f docker-compose.prod.yml logs -f"
    echo "Stop services:    docker-compose -f docker-compose.prod.yml down"
    echo "Restart services: docker-compose -f docker-compose.prod.yml restart"
    echo "View status:      docker-compose -f docker-compose.prod.yml ps"
    echo ""
    echo "🔄 The bot will automatically:"
    echo "- Post tweets every 12 hours (2 times per day)"
    echo "- Restart if it crashes (unless-stopped policy)"
    echo "- Catch up on missed posts when restarted"
    echo ""
    echo "🛡️  Security features enabled:"
    echo "- Content moderation and filtering"
    echo "- Daily cost limits and emergency stops"
    echo "- Health monitoring and auto-restart"
else
    echo "❌ Failed to start services. Check logs:"
    docker-compose -f docker-compose.prod.yml logs
    exit 1
fi

# Optional: Install as systemd service for server deployment
echo ""
read -p "🤖 Install as systemd service for automatic startup on boot? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if [ "$EUID" -eq 0 ]; then
        ./scripts/install-systemd-service.sh
    else
        echo "🔐 Installing systemd service (requires sudo)..."
        sudo ./scripts/install-systemd-service.sh
    fi
fi

echo ""
echo "🎉 Twitter Persona Agents is now running 24/7!"
echo "Monitor at: http://localhost:8582"