# Production-ready Dockerfile for TTS API Service
# Following FastAPI Docker best practices 2026

# Use Python slim image for smaller size (156MB vs 259MB with full image)
FROM python:3.10-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    COQUI_TOS_AGREED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    git \
    ffmpeg \
    pkg-config \
    espeak-ng \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# ============================================
# Builder stage - Install Python dependencies
# ============================================
FROM base AS builder

# Enable pip cache for faster rebuilds with BuildKit
ENV PIP_NO_CACHE_DIR=0

# Upgrade pip, setuptools, wheel
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel

# Copy requirements first for Docker layer caching
COPY requirements.txt /app/requirements.txt

# Install all dependencies with pinned versions
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user -r /app/requirements.txt

# ============================================
# Final stage - Copy only necessary files
# ============================================
FROM base

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy API service code
COPY app.py /app/api_service/app.py
COPY tts_gpu_worker.py /app/api_service/tts_gpu_worker.py

# Create voices directory
RUN mkdir -p /app/api_service/voices

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Run with single worker (recommended for CPU-bound tasks like TTS)
CMD ["uvicorn", "api_service.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
