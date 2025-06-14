#!/bin/bash

# Zen Kink Bot - Local Development Startup Script
# This script sets up and starts the application locally with all dependencies

set -e  # Exit on any error

echo "🧘 Starting Zen Kink Bot locally..."

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

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "🐍 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# # Install/update dependencies
# echo "📦 Installing dependencies..."
# pip install -r requirements.txt

# # Check if data directory exists
# if [ ! -d "data" ]; then
#     echo "📁 Creating data directory..."
#     mkdir -p data/{chroma,logs,backups,source_material}
# fi

# # Check if knowledge base exists
# if [ ! -d "data/chroma" ] || [ -z "$(ls -A data/chroma 2>/dev/null)" ]; then
#     echo "⚠️  Warning: Knowledge base appears empty."
#     echo "   Add PDF files to data/source_material/ and run:"
#     echo "   python -m ingest.split_embed"
#     echo ""
# fi

# Start Redis if not already running (for local development)
if ! pgrep -x "redis-server" > /dev/null; then
    echo "🔴 Starting Redis..."
    if command -v redis-server &> /dev/null; then
        redis-server --daemonize yes --port 6379
        echo "✅ Redis started on port 6379"
    else
        echo "⚠️  Redis not found. Install with: brew install redis (macOS) or apt install redis (Ubuntu)"
        echo "   Continuing without Redis (some features may be limited)"
    fi
else
    echo "✅ Redis already running"
fi

# Set environment variables
export PYTHONPATH=/Users/leojiang/Desktop/workspace/zenkink-twitter-agent
export ENVIRONMENT=development

# Start the application
echo "🚀 Starting Zen Kink Bot..."
echo ""
echo "🎛️  Control Panel: http://localhost:8582"
echo "🔍 Health Check:  http://localhost:8582/health"
echo "📊 Deep Health:   http://localhost:8582/health/deep"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8583 --reload