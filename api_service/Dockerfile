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

# Install core TTS dependencies (English-only, skip Japanese/Bangla/Korean)
RUN pip install --no-cache-dir \
    numpy>=1.24.3 \
    cython>=0.29.30 \
    scipy>=1.11.2 \
    torch>=2.1 \
    torchaudio \
    soundfile>=0.12.0 \
    librosa>=0.10.0 \
    scikit-learn>=1.3.0 \
    numba>=0.57.0 \
    inflect>=5.6.0 \
    tqdm>=4.64.1 \
    anyascii>=0.3.0 \
    pyyaml>=6.0 \
    fsspec>=2023.6.0 \
    aiohttp>=3.8.1 \
    packaging>=23.1 \
    mutagen==1.47.0 \
    pysbd>=0.3.4 \
    umap-learn>=0.5.1 \
    "pandas>=1.4,<2.0" \
    matplotlib>=3.7.0 \
    trainer>=0.0.36 \
    coqpit>=0.0.16 \
    einops>=0.6.0 \
    transformers>=4.33.0 \
    encodec>=0.1.1 \
    unidecode>=1.3.2 \
    num2words \
    nltk

# Install TTS library in development mode (without pulling extra deps)
RUN pip install --no-cache-dir --no-deps -e .

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
