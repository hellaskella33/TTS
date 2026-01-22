#!/usr/bin/env python3
"""
GPU TTS worker for Upstash Redis jobs.

Required env vars:
  UPSTASH_REDIS_REST_URL
  UPSTASH_REDIS_REST_TOKEN
  COQUI_TTS_SERVICE_URL
  VPS_HOST
  VPS_USER
  VPS_SSH_KEY_PATH

Optional env vars:
  TTS_JOBS_QUEUE (default: tts:jobs)
  TTS_RESULTS_QUEUE (default: tts:results)
  IDLE_SHUTDOWN_SECONDS (default: 120)
  POLL_INTERVAL_SECONDS (default: 2)
  VPS_BASE_DIR (used when audio_path is relative)
  VPS_PORT (default: 22)

Run:
  python tts_gpu_worker.py
"""

import base64
import json
import os
import posixpath
import random
import signal
import sys
import tempfile
import time
from typing import Any, Dict, Optional, Tuple

import paramiko
import requests
from upstash_redis import Redis

DEFAULT_JOBS_QUEUE = "tts:jobs"
DEFAULT_RESULTS_QUEUE = "tts:results"
DEFAULT_IDLE_SHUTDOWN = 120
DEFAULT_POLL_INTERVAL = 2.0

STOP_REQUESTED = False


def _handle_sigterm(signum, frame):
    del signum, frame
    global STOP_REQUESTED
    STOP_REQUESTED = True
    log_event("info", "shutdown requested", signal="SIGTERM")


def log_event(level: str, message: str, **fields: Any) -> None:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "msg": message,
    }
    record.update(fields)
    print(json.dumps(record, ensure_ascii=True), flush=True)


def retry(
    func,
    *,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_exceptions: Tuple[type, ...] = (Exception,),
    on_retry=None,
):
    attempt = 0
    while True:
        try:
            return func()
        except retry_exceptions as exc:
            attempt += 1
            if attempt >= max_attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = delay + random.uniform(0, delay * 0.1)
            if on_retry:
                on_retry(exc, attempt, delay)
            time.sleep(delay)


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return value


def build_coqui_url(base_url: str) -> str:
    if base_url.rstrip("/").endswith("/generate-audio"):
        return base_url
    return base_url.rstrip("/") + "/generate-audio"


def parse_job(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload)
    raise ValueError("unsupported payload type")


def download_audio(url: str) -> bytes:
    def _download():
        response = requests.get(url, timeout=(10, 300))
        response.raise_for_status()
        return response.content

    return retry(
        _download,
        on_retry=lambda exc, attempt, delay: log_event(
            "warning",
            "audio download retry",
            error=str(exc),
            attempt=attempt,
            delay_seconds=round(delay, 2),
        ),
    )


def request_tts(text: str, voice_name: str, service_url: str) -> Tuple[bytes, Optional[Any], Optional[str]]:
    url = build_coqui_url(service_url)

    def _request():
        response = requests.post(
            url,
            json={"text": text, "voice_name": voice_name, "output_format": "mp3"},
            timeout=(10, 300),
        )
        response.raise_for_status()
        return response

    response = retry(
        _request,
        on_retry=lambda exc, attempt, delay: log_event(
            "warning",
            "tts request retry",
            error=str(exc),
            attempt=attempt,
            delay_seconds=round(delay, 2),
        ),
    )

    content_type = response.headers.get("content-type", "")
    word_timestamps = None
    audio_url = None
    audio_bytes = b""

    if "application/json" in content_type:
        data = response.json()
        word_timestamps = data.get("word_timestamps")
        audio_url = data.get("audio_url")
        if data.get("audio_base64"):
            audio_bytes = base64.b64decode(data["audio_base64"])
        elif data.get("audio_bytes"):
            audio_bytes = base64.b64decode(data["audio_bytes"])
        elif audio_url:
            audio_bytes = download_audio(audio_url)
        else:
            raise RuntimeError("TTS response missing audio payload")
    else:
        audio_bytes = response.content

    if not audio_bytes:
        raise RuntimeError("TTS response contained empty audio")

    return audio_bytes, word_timestamps, audio_url


def resolve_remote_path(audio_path: str, base_dir: Optional[str]) -> str:
    if posixpath.isabs(audio_path):
        return audio_path
    if not base_dir:
        raise ValueError("VPS_BASE_DIR must be set when audio_path is relative")
    return posixpath.normpath(posixpath.join(base_dir, audio_path))


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    if not remote_dir or remote_dir == "/":
        return
    parts = []
    while remote_dir not in ("", "/"):
        parts.append(remote_dir)
        remote_dir = posixpath.dirname(remote_dir)
    for path in reversed(parts):
        try:
            sftp.stat(path)
        except OSError:
            sftp.mkdir(path)


def upload_file(
    local_path: str,
    remote_path: str,
    *,
    host: str,
    user: str,
    key_path: str,
    port: int,
) -> None:
    def _upload():
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=host,
            username=user,
            key_filename=key_path,
            port=port,
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            look_for_keys=False,
        )
        try:
            sftp = ssh.open_sftp()
            try:
                ensure_remote_dir(sftp, posixpath.dirname(remote_path))
                sftp.put(local_path, remote_path)
            finally:
                sftp.close()
        finally:
            ssh.close()

    retry(
        _upload,
        on_retry=lambda exc, attempt, delay: log_event(
            "warning",
            "upload retry",
            error=str(exc),
            attempt=attempt,
            delay_seconds=round(delay, 2),
        ),
    )


def push_result(redis: Redis, queue: str, payload: Dict[str, Any]) -> None:
    def _push():
        redis.rpush(queue, json.dumps(payload))

    retry(
        _push,
        on_retry=lambda exc, attempt, delay: log_event(
            "warning",
            "redis rpush retry",
            error=str(exc),
            attempt=attempt,
            delay_seconds=round(delay, 2),
        ),
    )


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_sigterm)

    redis_url = get_env("UPSTASH_REDIS_REST_URL")
    redis_token = get_env("UPSTASH_REDIS_REST_TOKEN")
    coqui_url = get_env("COQUI_TTS_SERVICE_URL")
    vps_host = get_env("VPS_HOST")
    vps_user = get_env("VPS_USER")
    vps_key = get_env("VPS_SSH_KEY_PATH")

    if not redis_url or not redis_token:
        log_event("error", "missing redis env vars")
        return 2
    if not coqui_url:
        log_event("error", "missing COQUI_TTS_SERVICE_URL")
        return 2
    if not vps_host or not vps_user or not vps_key:
        log_event("error", "missing VPS connection env vars")
        return 2

    jobs_queue = get_env("TTS_JOBS_QUEUE", DEFAULT_JOBS_QUEUE)
    results_queue = get_env("TTS_RESULTS_QUEUE", DEFAULT_RESULTS_QUEUE)
    idle_shutdown_seconds = int(get_env("IDLE_SHUTDOWN_SECONDS", str(DEFAULT_IDLE_SHUTDOWN)))
    poll_interval = float(get_env("POLL_INTERVAL_SECONDS", str(DEFAULT_POLL_INTERVAL)))
    vps_port = int(get_env("VPS_PORT", "22"))
    vps_base_dir = get_env("VPS_BASE_DIR")

    redis = Redis(url=redis_url, token=redis_token)

    log_event(
        "info",
        "worker started",
        jobs_queue=jobs_queue,
        results_queue=results_queue,
        idle_shutdown_seconds=idle_shutdown_seconds,
    )

    last_job_time = time.time()

    while not STOP_REQUESTED:
        try:
            payload = retry(
                lambda: redis.lpop(jobs_queue),
                on_retry=lambda exc, attempt, delay: log_event(
                    "warning",
                    "redis lpop retry",
                    error=str(exc),
                    attempt=attempt,
                    delay_seconds=round(delay, 2),
                ),
            )
        except Exception as exc:
            log_event("error", "redis lpop failed", error=str(exc))
            time.sleep(poll_interval)
            continue

        if payload is None:
            if time.time() - last_job_time >= idle_shutdown_seconds:
                log_event("info", "idle shutdown", idle_seconds=idle_shutdown_seconds)
                break
            time.sleep(poll_interval)
            continue

        last_job_time = time.time()

        try:
            job = parse_job(payload)
        except Exception as exc:
            log_event("error", "invalid job payload", error=str(exc))
            continue

        job_id = job.get("job_id", "unknown")
        voice_provider = job.get("voice_provider")
        script = job.get("script")
        voice_name = job.get("voice")
        audio_path = job.get("audio_path")

        if voice_provider != "coqui":
            push_result(redis, results_queue, {"job_id": job_id, "error": "unsupported provider"})
            log_event("warning", "unsupported voice provider", job_id=job_id, provider=voice_provider)
            continue

        if not script or not voice_name or not audio_path:
            push_result(redis, results_queue, {"job_id": job_id, "error": "missing required job fields"})
            log_event("error", "job missing required fields", job_id=job_id)
            continue

        try:
            audio_bytes, word_timestamps, audio_url = request_tts(script, voice_name, coqui_url)
            remote_path = resolve_remote_path(audio_path, vps_base_dir)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                temp_file.write(audio_bytes)
                local_path = temp_file.name

            try:
                upload_file(
                    local_path,
                    remote_path,
                    host=vps_host,
                    user=vps_user,
                    key_path=vps_key,
                    port=vps_port,
                )
            finally:
                try:
                    os.unlink(local_path)
                except OSError:
                    log_event("warning", "failed to remove temp file", path=local_path)

            result = {
                "job_id": job_id,
                "audio_path": remote_path,
            }
            if audio_url:
                result["audio_url"] = audio_url
            if word_timestamps is not None:
                result["word_timestamps"] = word_timestamps

            push_result(redis, results_queue, result)
            log_event("info", "job processed", job_id=job_id, audio_path=remote_path)
        except Exception as exc:
            push_result(redis, results_queue, {"job_id": job_id, "error": str(exc)})
            log_event("error", "job failed", job_id=job_id, error=str(exc))

    log_event("info", "worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
