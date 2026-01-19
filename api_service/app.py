"""
FastAPI TTS Service for YouTube Video Generation
Uses Coqui TTS with VCTK VITS model (109 pre-built English voices)
Optimized for GPU inference with audio format conversion support
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Optional
import torch
from TTS.api import TTS
import base64
import io
import os
import tempfile
import logging
from datetime import datetime
from pydub import AudioSegment
import hashlib
import re
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="TTS API Service",
    description="High-quality Text-to-Speech API for YouTube video generation using Coqui TTS",
    version="1.0.0"
)

# Global variables
tts_model = None
device = None
MODEL_NAME = "tts_models/en/vctk/vits"

def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

DEFAULT_CHUNK_SIZE = max(1, _int_env("TTS_CHUNK_SIZE", 800))
DEFAULT_CHUNK_SILENCE_MS = max(0, _int_env("TTS_CHUNK_SILENCE_MS", 0))
tts_lock = threading.Lock()

# Pydantic models for request/response
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to convert to speech")
    voice_name: str = Field(default="p225", description="Speaker ID from VCTK dataset (e.g., p225, p226, etc.)")
    output_format: str = Field(default="mp3", description="Output audio format: mp3 or wav")
    sample_rate: int = Field(default=44100, description="Sample rate in Hz (22050, 44100, or 48000)")
    audio_description: Optional[str] = Field(default="", description="Optional context about the audio (not used by model)")

class TTSResponse(BaseModel):
    success: bool
    audio_base64: str
    format: str
    sample_rate: int
    duration_seconds: float
    voice_used: str
    text_length: int
    generation_time_ms: float

class VoiceInfo(BaseModel):
    voice_id: str
    description: str

class HealthResponse(BaseModel):
    status: str
    device: str
    model_loaded: bool
    model_name: str
    available_voices_count: int

def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text.strip()]

    chunks = []
    paragraphs = re.split(r"\n{2,}", text.strip())
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(current) + len(sentence) + (1 if current else 0) <= max_chars:
                current = f"{current} {sentence}".strip()
                continue
            if current:
                chunks.append(current)
            if len(sentence) <= max_chars:
                current = sentence
                continue
            words = sentence.split()
            word_chunk = ""
            for word in words:
                if len(word_chunk) + len(word) + (1 if word_chunk else 0) <= max_chars:
                    word_chunk = f"{word_chunk} {word}".strip()
                else:
                    if word_chunk:
                        chunks.append(word_chunk)
                    word_chunk = word
            current = word_chunk
        if current:
            chunks.append(current)
    return chunks

def _synthesize_audio(text: str, voice_name: str, sample_rate: int) -> AudioSegment:
    chunks = _split_text(text, DEFAULT_CHUNK_SIZE)
    combined = AudioSegment.empty()

    for chunk in chunks:
        temp_wav_path = None
        try:
            with tts_lock, torch.inference_mode():
                wav = tts_model.tts(text=chunk, speaker=voice_name)
                temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                temp_wav_path = temp_wav.name
                temp_wav.close()
                tts_model.synthesizer.save_wav(wav=wav, path=temp_wav_path)

            audio = AudioSegment.from_wav(temp_wav_path)
            if sample_rate != audio.frame_rate:
                audio = audio.set_frame_rate(sample_rate)

            combined += audio
            if DEFAULT_CHUNK_SILENCE_MS > 0:
                combined += AudioSegment.silent(duration=DEFAULT_CHUNK_SILENCE_MS)
        finally:
            if temp_wav_path and os.path.exists(temp_wav_path):
                os.remove(temp_wav_path)

    return combined

# Startup event - Load TTS model
@app.on_event("startup")
async def startup_event():
    global tts_model, device

    logger.info("Starting TTS API Service...")

    # Detect device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")

    if device == "cpu":
        logger.warning("GPU not available. Running on CPU will be slower.")

    # Load TTS model
    try:
        logger.info(f"Loading TTS model: {MODEL_NAME}")
        tts_model = TTS(MODEL_NAME, progress_bar=False, gpu=(device=="cuda"))
        tts_model.to(device)
        logger.info(f"Model loaded successfully with {len(tts_model.speakers)} voices")
    except Exception as e:
        logger.error(f"Failed to load TTS model: {str(e)}")
        raise

@app.get("/", response_class=JSONResponse)
async def root():
    """Root endpoint with API information"""
    return {
        "service": "TTS API for YouTube Video Generation",
        "version": "1.0.0",
        "model": MODEL_NAME,
        "endpoints": {
            "generate_audio": "POST /generate-audio",
            "list_voices": "GET /voices",
            "health_check": "GET /health"
        },
        "documentation": "/docs"
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy" if tts_model is not None else "unhealthy",
        device=device,
        model_loaded=tts_model is not None,
        model_name=MODEL_NAME,
        available_voices_count=len(tts_model.speakers) if tts_model else 0
    )

@app.get("/voices")
async def list_voices():
    """List all available voice speakers"""
    if tts_model is None:
        raise HTTPException(status_code=503, detail="TTS model not loaded")

    # Create voice descriptions (VCTK speakers)
    voices = []
    for speaker_id in tts_model.speakers:
        # Extract speaker number and provide basic info
        voices.append({
            "voice_id": speaker_id,
            "description": f"VCTK Speaker {speaker_id}"
        })

    return {
        "total_voices": len(voices),
        "voices": voices,
        "model": MODEL_NAME,
        "note": "VCTK dataset contains 109 English speakers with various accents (British, American, etc.)"
    }

@app.post("/generate-audio", response_model=TTSResponse)
def generate_audio(request: TTSRequest):
    """
    Generate speech audio from text using selected voice

    This endpoint converts text to speech and returns base64-encoded audio
    optimized for YouTube video narration.
    """
    if tts_model is None:
        raise HTTPException(status_code=503, detail="TTS model not loaded")

    # Validate voice_name
    if request.voice_name not in tts_model.speakers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice_name: {request.voice_name}. Use /voices endpoint to see available voices."
        )

    # Validate output format
    if request.output_format not in ["mp3", "wav"]:
        raise HTTPException(status_code=400, detail="output_format must be 'mp3' or 'wav'")

    # Validate sample rate
    if request.sample_rate not in [22050, 44100, 48000]:
        raise HTTPException(status_code=400, detail="sample_rate must be 22050, 44100, or 48000")

    start_time = datetime.now()

    try:
        logger.info(f"Generating audio for text length: {len(request.text)} with voice: {request.voice_name}")

        audio = _synthesize_audio(
            text=request.text,
            voice_name=request.voice_name,
            sample_rate=request.sample_rate
        )

        # Export to requested format
        audio_buffer = io.BytesIO()
        if request.output_format == "mp3":
            audio.export(audio_buffer, format="mp3", bitrate="192k")
        else:
            audio.export(audio_buffer, format="wav")

        audio_buffer.seek(0)
        audio_data = base64.b64encode(audio_buffer.read()).decode()

        # Calculate generation time
        generation_time = (datetime.now() - start_time).total_seconds() * 1000

        # Calculate duration
        duration = audio.duration_seconds

        logger.info(f"Audio generated successfully in {generation_time:.2f}ms")

        return TTSResponse(
            success=True,
            audio_base64=audio_data,
            format=request.output_format,
            sample_rate=request.sample_rate,
            duration_seconds=duration,
            voice_used=request.voice_name,
            text_length=len(request.text),
            generation_time_ms=generation_time
        )

    except Exception as e:
        logger.error(f"Error generating audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audio generation failed: {str(e)}")

@app.post("/generate-audio-file")
def generate_audio_file(request: TTSRequest):
    """
    Generate speech audio and return as downloadable file
    Alternative to base64 encoding for large files
    """
    if tts_model is None:
        raise HTTPException(status_code=503, detail="TTS model not loaded")

    if request.voice_name not in tts_model.speakers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice_name: {request.voice_name}"
        )

    if request.output_format not in ["mp3", "wav"]:
        raise HTTPException(status_code=400, detail="output_format must be 'mp3' or 'wav'")

    if request.sample_rate not in [22050, 44100, 48000]:
        raise HTTPException(status_code=400, detail="sample_rate must be 22050, 44100, or 48000")

    temp_out_path = None
    cleanup_out = True

    try:
        audio = _synthesize_audio(
            text=request.text,
            voice_name=request.voice_name,
            sample_rate=request.sample_rate
        )

        # Create unique filename
        file_id = hashlib.md5(request.text.encode()).hexdigest()[:8]
        filename = f"tts_{file_id}.{request.output_format}"

        temp_out = tempfile.NamedTemporaryFile(
            suffix=f".{request.output_format}",
            delete=False,
            dir="/tmp"
        )
        temp_out_path = temp_out.name
        temp_out.close()

        if request.output_format == "mp3":
            audio.export(temp_out_path, format="mp3", bitrate="192k")
        else:
            audio.export(temp_out_path, format="wav")

        background_tasks = BackgroundTasks()
        background_tasks.add_task(os.remove, temp_out_path)
        cleanup_out = False

        return FileResponse(
            path=temp_out_path,
            media_type=f"audio/{request.output_format}",
            filename=filename,
            background=background_tasks
        )

    except Exception as e:
        logger.error(f"Error generating audio file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cleanup_out and temp_out_path and os.path.exists(temp_out_path):
            os.remove(temp_out_path)

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
