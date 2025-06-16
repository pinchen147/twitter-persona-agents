# Production Dockerfile for Twitter Persona Agents
# 
# This Dockerfile creates a minimal production-ready container for the bot system.
# It uses Python 3.11 slim base image for optimal size/performance balance.
#
# Features:
# - Multi-stage build optimization (if needed in future)
# - Non-root user for security
# - Health checks for container orchestration
# - Minimal attack surface with only required dependencies
#
# Build: docker build -f docker/Dockerfile -t twitter-persona-agents .
# Run: docker run -p 8000:8000 --env-file .env twitter-persona-agents

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data/chroma data/logs data/backups

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]