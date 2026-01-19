# TTS API Service for YouTube Video Generation

High-performance Text-to-Speech FastAPI service powered by Coqui TTS with GPU acceleration. Designed for AI video generation workflows with 109 pre-built English narrator voices.

## Features

- **109 Pre-Built English Voices** - VCTK dataset with diverse accents and genders
- **GPU Accelerated** - NVIDIA CUDA support for fast inference
- **Production Ready** - Docker containerization with health checks
- **YouTube Optimized** - High-quality audio output (MP3/WAV) at customizable sample rates
- **RESTful API** - Clean FastAPI interface with automatic documentation
- **Base64 & File Response** - Flexible audio delivery options

## Quick Start

### Prerequisites

**Hardware:**
- NVIDIA GPU (recommended, 4GB+ VRAM)
- 8GB+ System RAM

**Software:**
- Docker with GPU support (nvidia-docker2)
- NVIDIA drivers installed on host

### Installation

#### 1. Setup GPU Support (Ubuntu/Linux)

```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Test GPU access
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

#### 2. Setup GPU Support (Windows with WSL2)

```bash
# 1. Install WSL2 and Docker Desktop
# 2. Install NVIDIA drivers for Windows
# 3. Enable GPU in Docker Desktop: Settings > Resources > WSL Integration
# 4. Test:
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

#### 3. Build and Run

```bash
cd api_service

# GPU (Windows/Linux - WSL2)
docker compose up -d --build

# CPU (macOS)
docker compose -f docker-compose.cpu.yml up -d --build

# Check logs
docker compose logs -f
# or (CPU)
docker compose -f docker-compose.cpu.yml logs -f

# Check health
curl http://localhost:8000/health
```

The API will be available at `http://localhost:8000`

## API Documentation

### Interactive API Docs

Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Endpoints

#### 1. Generate Audio (Base64 Response)

**POST** `/generate-audio`

Convert text to speech and return base64-encoded audio.

**Request Body:**
```json
{
  "text": "Welcome to my YouTube video! Today we're going to explore...",
  "voice_name": "p225",
  "output_format": "mp3",
  "sample_rate": 44100,
  "audio_description": "Energetic video intro"
}
```

**Parameters:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| text | string | Yes | - | Text to synthesize (1-5000 chars) |
| voice_name | string | Yes | p225 | Speaker ID (see /voices endpoint) |
| output_format | string | No | mp3 | Audio format: `mp3` or `wav` |
| sample_rate | integer | No | 44100 | Sample rate: 22050, 44100, or 48000 Hz |
| audio_description | string | No | "" | Optional context (for future use) |

**Response:**
```json
{
  "success": true,
  "audio_base64": "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU5LjI3LjEwMAAAAAAAAAAAAAAA...",
  "format": "mp3",
  "sample_rate": 44100,
  "duration_seconds": 12.5,
  "voice_used": "p225",
  "text_length": 256,
  "generation_time_ms": 1234.56
}
```

**Python Example:**
```python
import requests
import base64

response = requests.post(
    "http://localhost:8000/generate-audio",
    json={
        "text": "Hello, this is my YouTube narration!",
        "voice_name": "p225",
        "output_format": "mp3",
        "sample_rate": 44100
    }
)

data = response.json()

# Decode and save audio
audio_bytes = base64.b64decode(data["audio_base64"])
with open("output.mp3", "wb") as f:
    f.write(audio_bytes)

print(f"Generated {data['duration_seconds']} seconds of audio in {data['generation_time_ms']}ms")
```

#### 2. Generate Audio (File Download)

**POST** `/generate-audio-file`

Same parameters as above, but returns a downloadable audio file directly.

**Python Example:**
```python
response = requests.post(
    "http://localhost:8000/generate-audio-file",
    json={"text": "Hello world", "voice_name": "p225", "output_format": "mp3"}
)

with open("narration.mp3", "wb") as f:
    f.write(response.content)
```

#### 3. List Available Voices

**GET** `/voices`

Returns all 109 available voice speakers.

**Response:**
```json
{
  "total_voices": 109,
  "voices": [
    {"voice_id": "p225", "description": "VCTK Speaker p225"},
    {"voice_id": "p226", "description": "VCTK Speaker p226"},
    ...
  ],
  "model": "tts_models/en/vctk/vits",
  "note": "VCTK dataset contains 109 English speakers with various accents"
}
```

#### 4. Health Check

**GET** `/health`

Check service health and GPU status.

**Response:**
```json
{
  "status": "healthy",
  "device": "cuda",
  "model_loaded": true,
  "model_name": "tts_models/en/vctk/vits",
  "available_voices_count": 109
}
```

## Voice Selection Guide

The VCTK dataset contains 109 speakers with diverse characteristics:

- **Gender**: Male and female voices
- **Accents**: British English (various regions), American English, Irish, Scottish
- **Ages**: Range from young to mature voices

**Popular Voice IDs:**
- `p225`, `p226`, `p227` - Clear female voices
- `p232`, `p243`, `p254` - Clear male voices
- `p245`, `p248`, `p250` - Expressive female voices
- `p251`, `p252`, `p255` - Expressive male voices

**Finding Your Perfect Voice:**
```bash
# Test multiple voices
for voice in p225 p226 p232 p243; do
  curl -X POST http://localhost:8000/generate-audio \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"This is a test narration\",\"voice_name\":\"$voice\"}" \
    | jq -r '.audio_base64' | base64 -d > "test_$voice.mp3"
done
```

## Integration with AI Video Generator

### Example Integration Code

```python
import requests
import base64

class TTSService:
    def __init__(self, api_url="http://localhost:8000"):
        self.api_url = api_url
        self.default_voice = "p225"

    def generate_narration(self, script_text, voice=None, output_path="narration.mp3"):
        """Generate narration audio for video"""

        response = requests.post(
            f"{self.api_url}/generate-audio",
            json={
                "text": script_text,
                "voice_name": voice or self.default_voice,
                "output_format": "mp3",
                "sample_rate": 44100
            }
        )

        if response.status_code == 200:
            data = response.json()

            # Decode and save audio
            audio_bytes = base64.b64decode(data["audio_base64"])
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            return {
                "success": True,
                "audio_path": output_path,
                "duration": data["duration_seconds"],
                "generation_time": data["generation_time_ms"]
            }
        else:
            return {"success": False, "error": response.json()}

# Usage in your video generator
tts = TTSService()

# Generate narration
result = tts.generate_narration(
    script_text="Welcome to my AI-generated video about technology...",
    voice="p225",
    output_path="video_narration.mp3"
)

print(f"Audio saved to: {result['audio_path']}")
print(f"Duration: {result['duration']} seconds")
```

## Performance Benchmarks

**GPU (NVIDIA RTX 3060):**
- Model loading: ~5-10 seconds (one-time)
- 100 words: ~2-3 seconds
- 500 words: ~8-10 seconds
- 1000 words: ~15-20 seconds

**CPU (Intel i7):**
- Model loading: ~10-15 seconds
- 100 words: ~15-20 seconds
- 500 words: ~60-80 seconds
- 1000 words: ~120-150 seconds

**GPU acceleration provides 5-10x speedup!**

## Configuration

### Environment Variables

Create `.env` file in `api_service/` directory:

```bash
# GPU Configuration
CUDA_VISIBLE_DEVICES=0

# API Configuration
API_PORT=8000
API_WORKERS=1

# TTS Configuration
COQUI_TOS_AGREED=1

# Chunking for long scripts (optional)
TTS_CHUNK_SIZE=800
TTS_CHUNK_SILENCE_MS=0
```

### Custom Voice References

To use custom voice cloning (future feature), place reference audio files in:
```
api_service/voices/
├── narrator1.wav
├── narrator2.wav
└── professional_voice.wav
```

## Troubleshooting

### GPU Not Detected

```bash
# Check NVIDIA drivers
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# Check container GPU
docker-compose exec tts-api nvidia-smi
```

### Model Download Issues

Models are auto-downloaded on first run. If you encounter issues:

```bash
# Pre-download models
docker-compose exec tts-api python3 -c "from TTS.api import TTS; TTS('tts_models/en/vctk/vits')"
```

### Memory Issues

If running out of GPU memory:
- Reduce text length (split into smaller chunks)
- Lower sample rate to 22050 Hz
- Use CPU mode (slower but works)

### Port Already in Use

```bash
# Change port in docker-compose.yml
ports:
  - "8001:8000"  # Use port 8001 instead
```

## Production Deployment

### Security Considerations

1. **Add Authentication**:
```python
from fastapi.security import HTTPBearer
security = HTTPBearer()

@app.post("/generate-audio")
async def generate_audio(request: TTSRequest, credentials: HTTPBearer = Depends(security)):
    # Validate token
    pass
```

2. **Rate Limiting**:
```bash
pip install slowapi
```

3. **HTTPS/SSL**: Use reverse proxy (nginx) with SSL certificates

### Scaling

For high-traffic scenarios:

1. **Horizontal Scaling**: Run multiple containers behind a load balancer
2. **Caching**: Cache frequently generated audio
3. **Async Processing**: Use Celery/RQ for background processing
4. **GPU Pool**: Multiple GPUs with load balancing

## License

This FastAPI wrapper is provided under MIT License.

The underlying Coqui TTS library is licensed under Mozilla Public License 2.0 (MPL 2.0).
See `../LICENSE.txt` for Coqui TTS license details.

## Attribution

Built on [Coqui TTS](https://github.com/coqui-ai/TTS) - A deep learning toolkit for Text-to-Speech.

---

## Support

For issues specific to this API wrapper:
- Open an issue in this repository

For TTS model issues:
- Check [Coqui TTS GitHub](https://github.com/coqui-ai/TTS)

---

**Made for YouTube Video Generation** | **Powered by Coqui TTS**
