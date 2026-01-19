#!/bin/bash
# Stop script for TTS API Service

echo "Stopping TTS API Service..."

# Detect docker compose command
if docker compose version > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "Error: Docker Compose not found"
    exit 1
fi

# Detect which compose file was used
if [[ "$OSTYPE" == "darwin"* ]]; then
    COMPOSE_FILE="docker-compose.cpu.yml"
else
    # Try GPU first, fallback to CPU
    if docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
        COMPOSE_FILE="docker-compose.yml"
    else
        COMPOSE_FILE="docker-compose.cpu.yml"
    fi
fi

# Stop and remove containers
$DOCKER_COMPOSE -f $COMPOSE_FILE down

echo "Service stopped successfully"
