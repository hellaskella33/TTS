#!/bin/bash
# Quick start script for TTS API Service

set -e

echo "🚀 Starting TTS API Service..."
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker first."
    exit 1
fi

# Check for GPU support
if docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
    echo "✅ GPU support detected"
else
    echo "⚠️  Warning: GPU support not detected. Service will run on CPU (slower)."
    echo "   To enable GPU, install nvidia-container-toolkit on the host."
    echo ""
fi

# Build and start
echo "📦 Building Docker image (this may take a few minutes on first run)..."
docker-compose build

echo ""
echo "🎬 Starting API service..."
docker-compose up -d

echo ""
echo "⏳ Waiting for service to be healthy..."
sleep 10

# Wait for health check
for i in {1..30}; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo ""
        echo "✅ Service is ready!"
        echo ""
        echo "📖 API Documentation: http://localhost:8000/docs"
        echo "🎤 Available voices: http://localhost:8000/voices"
        echo "❤️  Health check: http://localhost:8000/health"
        echo ""
        echo "📊 View logs: docker-compose logs -f"
        echo "🛑 Stop service: docker-compose down"
        echo ""
        exit 0
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "⚠️  Service started but health check failed. Check logs with: docker-compose logs"
exit 1
