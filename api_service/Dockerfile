# GPU-enabled Dockerfile for TTS API Service
# Base image with CUDA support for GPU acceleration
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3-dev \
    ffmpeg \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python3 -m pip install --no-cache-dir --upgrade pip

# Copy requirements first (for better Docker layer caching)
COPY requirements.txt /app/api_service/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/api_service/requirements.txt

# Copy the entire TTS library source code
COPY TTS/ /app/TTS/
COPY setup.py /app/
COPY README.md /app/
COPY requirements.txt /app/

# Install TTS library in development mode
RUN pip install --no-cache-dir -e .

# Copy API service code
COPY api_service/ /app/api_service/

# Create directory for voice reference files
RUN mkdir -p /app/api_service/voices

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV COQUI_TOS_AGREED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the FastAPI application
CMD ["uvicorn", "api_service.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
