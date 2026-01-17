# Troubleshooting Guide

## Build Errors

### Error: "Failed building wheel for sudachipy" (Rust compiler required)

**Problem**: The full TTS library includes Japanese language support which requires Rust compiler.

**Solution**: The Dockerfile has been optimized to install only English dependencies. This skips:
- Japanese support (sudachipy, spacy[ja])
- Korean support (g2pkk, hangul_romanize, jamo)
- Bangla support (bangla, bnnumerizer, bnunicodenormalizer)
- Chinese support (jieba, pypinyin)
- French/German/Spanish support (gruut[de,es,fr])

These are not needed for English-only YouTube narration with VCTK VITS model.

**If you need other languages**, add Rust compiler to Dockerfile:
```dockerfile
RUN apt-get update && apt-get install -y \
    curl \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . $HOME/.cargo/env
```

---

## Docker Compose Errors

### Error: "docker-compose: command not found"

**Problem**: Modern Docker Desktop uses `docker compose` (V2) instead of `docker-compose` (V1).

**Solution**: Use the provided `start.sh` script which auto-detects the correct command, or run:
```bash
docker compose -f docker-compose.cpu.yml up -d
```

---

## Runtime Errors

### Error: Port 8000 already in use

**Solution**: Change the port in `docker-compose.yml` or `docker-compose.cpu.yml`:
```yaml
ports:
  - "8001:8000"  # Use port 8001 instead
```

Then access API at: http://localhost:8001

---

### Error: CUDA out of memory

**Problem**: GPU doesn't have enough VRAM for the model.

**Solutions**:
1. Use CPU mode instead: `docker-compose.cpu.yml`
2. Reduce batch size in code (if processing multiple requests)
3. Use a GPU with more VRAM (VCTK VITS needs ~2-4GB)

---

### Service won't start / Health check fails

**Check logs**:
```bash
# With start.sh
docker compose -f docker-compose.cpu.yml logs -f

# Or directly
docker logs tts-api-service
```

**Common issues**:
- Model download taking too long (first run can take 2-5 minutes)
- Out of memory (use smaller model or CPU mode)
- Port conflict (change port in docker-compose file)

---

## Performance Issues

### Slow inference on CPU

**Expected**: CPU inference is 5-10x slower than GPU.
- 100 words: ~15-20 seconds (CPU) vs 2-3 seconds (GPU)

**Solutions**:
1. Use GPU mode (Windows with NVIDIA GPU + Docker Desktop)
2. Pre-generate common phrases
3. Use caching for repeated text
4. Consider using a lighter model (though VCTK VITS is already optimized)

---

## Connection Issues

### Can't connect from another computer

**Check firewall** (Windows):
```powershell
New-NetFirewallRule -DisplayName "TTS API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

**Check Docker port binding**:
```bash
docker ps
# Should show: 0.0.0.0:8000->8000/tcp
```

**Verify from another computer**:
```bash
curl http://WINDOWS_IP:8000/health
```

---

## Model Download Issues

### Model download fails / times out

**Manual download**:
```bash
docker exec -it tts-api-service python3 -c "from TTS.api import TTS; TTS('tts_models/en/vctk/vits')"
```

**Use model cache volume**:
The docker-compose files already include a volume for caching:
```yaml
volumes:
  - tts-models-cache:/root/.local/share/tts
```

---

## Windows-Specific Issues

### WSL2 integration not working

1. Open Docker Desktop
2. Settings → Resources → WSL Integration
3. Enable integration with your WSL2 distro
4. Restart Docker Desktop

### GPU not detected on Windows

1. Install latest NVIDIA drivers for Windows (not WSL)
2. Verify: `nvidia-smi` in WSL2 should show GPU
3. Docker Desktop automatically passes GPU to WSL2

---

## macOS-Specific Issues

### GPU support on macOS

**Not Available**: macOS doesn't support NVIDIA CUDA.

**Solution**: Use CPU mode (automatic with `start.sh`):
```bash
docker compose -f docker-compose.cpu.yml up -d
```

Apple Silicon (M1/M2) acceleration is not currently supported by PyTorch CUDA builds.

---

## Development / Testing

### How to test without Docker

```bash
# Install dependencies
pip install -e .
pip install fastapi uvicorn pydub

# Run directly
cd api_service
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### How to rebuild after code changes

```bash
# Stop service
docker compose -f docker-compose.cpu.yml down

# Rebuild
docker compose -f docker-compose.cpu.yml build --no-cache

# Start
docker compose -f docker-compose.cpu.yml up -d
```

---

## Getting Help

1. Check logs first: `docker compose logs -f`
2. Verify Docker is running: `docker info`
3. Test health endpoint: `curl http://localhost:8000/health`
4. Check GitHub issues: https://github.com/hellaskella33/TTS/issues
5. Check original TTS repo: https://github.com/coqui-ai/TTS/issues
