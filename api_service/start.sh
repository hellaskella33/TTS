#!/bin/bash
# Quick start script for TTS API Service

set -e

echo "Starting TTS API Service..."
echo ""

TTS_API_PORT="${TTS_API_PORT:-8000}"
export TTS_API_PORT

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker first."
    exit 1
fi

# Detect docker compose command (V2 vs V1)
if docker compose version > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
    echo "Using Docker Compose V2"
elif command -v docker-compose > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
    echo "Using Docker Compose V1"
else
    echo "Error: Docker Compose not found. Please install Docker Desktop or docker-compose."
    exit 1
fi

# Check for GPU support and select appropriate compose file
COMPOSE_FILE="docker-compose.yml"

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Running on macOS - Using CPU-only configuration"
    COMPOSE_FILE="docker-compose.cpu.yml"
    echo ""
elif docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
    echo "GPU support detected - Using GPU-accelerated configuration"
    COMPOSE_FILE="docker-compose.yml"
else
    echo "Warning: GPU support not detected. Using CPU configuration (slower)."
    echo "   To enable GPU, install nvidia-container-toolkit on the host."
    COMPOSE_FILE="docker-compose.cpu.yml"
    echo ""
fi

# Build and start
echo "Using host port ${TTS_API_PORT}"
echo "Building Docker image (this may take a few minutes on first run)..."
$DOCKER_COMPOSE -f $COMPOSE_FILE build

echo ""
echo "Starting API service..."
$DOCKER_COMPOSE -f $COMPOSE_FILE up -d

echo ""
echo "Waiting for service to be healthy..."
sleep 10

# Wait for health check
for i in {1..30}; do
    if curl -f http://localhost:${TTS_API_PORT}/health > /dev/null 2>&1; then
        echo ""
        echo "Service is ready!"
        echo ""
        echo "API Documentation: http://localhost:${TTS_API_PORT}/docs"
        echo "Available voices: http://localhost:${TTS_API_PORT}/voices"
        echo "Health check: http://localhost:${TTS_API_PORT}/health"
        echo ""
        echo "View logs: $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
        echo "Stop service: $DOCKER_COMPOSE -f $COMPOSE_FILE down"
        echo ""
        exit 0
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "Service started but health check failed. Check logs with: $DOCKER_COMPOSE -f $COMPOSE_FILE logs"
exit 1
