#!/bin/bash

# Zen Kink Bot - Docker Startup Script
# This script builds/updates the Docker image and starts the application with Redis

set -e  # Exit on any error
export COMPOSE_PROJECT_NAME="zenkink-twitter-bot"

echo "🐳 Starting Zen Kink Bot with Docker..."

# Check if .env file exists (in root or config directory)
if [ ! -f .env ] && [ ! -f config/.env ]; then
    echo "❌ Error: .env file not found!"
    echo "   Please copy config/secrets.env.example to .env or config/.env and add your API keys"
    exit 1
fi

# Use config/.env if .env doesn't exist in root
if [ ! -f .env ] && [ -f config/.env ]; then
    echo "📝 Using config/.env file..."
    cp config/.env .env
fi

# Check if data directory exists
if [ ! -d "data" ]; then
    echo "📁 Creating data directory..."
    mkdir -p data/{chroma,logs,backups,source_material}
fi

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose -f docker/docker-compose.yml down 2>/dev/null || true

# Build/update the Docker image
echo "🔨 Building Docker image..."
docker-compose -f docker/docker-compose.yml build

# Start the services
echo "🚀 Starting services..."
docker-compose -f docker/docker-compose.yml up -d

# Wait a moment for services to initialize
echo "⏳ Waiting for services to start..."
sleep 5

# Check if services are running
if docker-compose -f docker/docker-compose.yml ps | grep -q "Up"; then
    echo "✅ Services started successfully!"
    echo ""
    echo "🎛️  Control Panel: http://localhost:8582"
    echo "🔍 Health Check:  http://localhost:8000/health"
    echo "📊 Deep Health:   http://localhost:8000/health/deep"
    echo ""
    echo "📋 To view logs: docker-compose -f docker/docker-compose.yml logs -f"
    echo "🛑 To stop:      docker-compose -f docker/docker-compose.yml down"
else
    echo "❌ Failed to start services. Check logs:"
    docker-compose -f docker/docker-compose.yml logs
    exit 1
fi