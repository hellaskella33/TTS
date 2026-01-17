"""
FastAPI TTS Service for YouTube Video Generation
Uses Coqui TTS with VCTK VITS model (109 pre-built English voices)
Optimized for GPU inference with audio format conversion support
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List
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
import uuid

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

# Pydantic models for request/response
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Text to convert to speech (1-5000 characters)")
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
async def generate_audio(request: TTSRequest):
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

        # Generate speech
        wav = tts_model.tts(
            text=request.text,
            speaker=request.voice_name
        )

        # Save to temporary WAV file
        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_wav_path = temp_wav.name
        temp_wav.close()

        tts_model.synthesizer.save_wav(wav=wav, path=temp_wav_path)

        # Convert to requested format and sample rate
        audio = AudioSegment.from_wav(temp_wav_path)

        # Resample if needed
        if request.sample_rate != audio.frame_rate:
            audio = audio.set_frame_rate(request.sample_rate)

        # Export to requested format
        audio_buffer = io.BytesIO()
        if request.output_format == "mp3":
            audio.export(audio_buffer, format="mp3", bitrate="192k")
        else:
            audio.export(audio_buffer, format="wav")

        audio_buffer.seek(0)
        audio_data = base64.b64encode(audio_buffer.read()).decode()

        # Clean up temp file
        os.remove(temp_wav_path)

        # Calculate generation time
        generation_time = (datetime.now() - start_time).total_seconds() * 1000

        # Calculate duration
        duration = len(wav) / 22050  # VITS outputs at 22050 Hz

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
async def generate_audio_file(request: TTSRequest):
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

    try:
        # Generate speech
        wav = tts_model.tts(
            text=request.text,
            speaker=request.voice_name
        )

        # Create unique filename
        file_id = hashlib.md5(request.text.encode()).hexdigest()[:8]
        filename = f"tts_{file_id}.{request.output_format}"

        # Save to temp file
        temp_file = tempfile.NamedTemporaryFile(
            suffix=f".{request.output_format}",
            delete=False,
            dir="/tmp"
        )
        temp_path = temp_file.name
        temp_file.close()

        # Export with conversion
        audio = AudioSegment.from_wav(io.BytesIO(wav.tobytes()))
        audio = audio.set_frame_rate(request.sample_rate)

        if request.output_format == "mp3":
            audio.export(temp_path, format="mp3", bitrate="192k")
        else:
            audio.export(temp_path, format="wav")

        return FileResponse(
            path=temp_path,
            media_type=f"audio/{request.output_format}",
            filename=filename,
            background=BackgroundTasks().add_task(os.remove, temp_path)
        )

    except Exception as e:
        logger.error(f"Error generating audio file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
