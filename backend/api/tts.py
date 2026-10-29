"""
Kokoro TTS API — Text-to-Speech via Kokoro (PyTorch)
=====================================================
Voice .pt files live in backend/models/kokoro/voices/
The main model is auto-cached by the kokoro package (~/.cache/huggingface).

Install: pip install kokoro soundfile
"""
import io
import logging
import pathlib
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("rhizomatic.tts")

VOICES_DIR = pathlib.Path(__file__).parent.parent / "models" / "kokoro" / "voices"

KOKORO_VOICES = {
    "af_bella":    "Bella · American ♀",
    "af_nicole":   "Nicole · American ♀",
    "af_sarah":    "Sarah · American ♀",
    "af_sky":      "Sky · American ♀",
    "am_adam":     "Adam · American ♂",
    "am_michael":  "Michael · American ♂",
    "bf_emma":     "Emma · British ♀",
    "bf_isabella": "Isabella · British ♀",
    "bm_george":   "George · British ♂",
    "bm_lewis":    "Lewis · British ♂",
}

_pipeline = None
_pipeline_error: str | None = None


def _load_pipeline():
    global _pipeline, _pipeline_error
    if _pipeline is not None:
        return _pipeline
    if _pipeline_error is not None:
        raise HTTPException(503, _pipeline_error)

    try:
        from kokoro import KPipeline  # type: ignore
    except ImportError:
        _pipeline_error = "kokoro not installed. Run: pip install kokoro soundfile"
        raise HTTPException(503, _pipeline_error)

    try:
        logger.info("Loading Kokoro pipeline (first run downloads ~300MB to HF cache)...")
        _pipeline = KPipeline(lang_code="a")
        logger.info("Kokoro TTS pipeline ready.")
        return _pipeline
    except Exception as e:
        _pipeline_error = f"Kokoro init failed: {e}"
        logger.error(_pipeline_error)
        raise HTTPException(503, _pipeline_error)


class TTSRequest(BaseModel):
    text: str
    voice: str = "af_bella"
    speed: float = 1.0


@router.post("/tts/speak")
async def speak(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(400, "Text is empty")
    if req.voice not in KOKORO_VOICES:
        raise HTTPException(400, f"Unknown voice '{req.voice}'")
    if not (0.5 <= req.speed <= 2.0):
        raise HTTPException(400, "Speed must be 0.5–2.0")

    pipeline = _load_pipeline()

    try:
        import soundfile as sf  # type: ignore
        import numpy as np
    except ImportError:
        raise HTTPException(503, "soundfile not installed. Run: pip install soundfile")

    voice_path = VOICES_DIR / f"{req.voice}.pt"
    if not voice_path.exists():
        raise HTTPException(503, f"Voice file not found: {voice_path}")

    try:
        text = req.text[:5000]
        audio_chunks = []
        generator = pipeline(text, voice=str(voice_path), speed=req.speed)
        for _, _, audio in generator:
            if audio is not None:
                audio_chunks.append(audio)

        if not audio_chunks:
            raise HTTPException(500, "No audio generated")

        combined = np.concatenate(audio_chunks)
        buf = io.BytesIO()
        sf.write(buf, combined, 24000, format="WAV")
        buf.seek(0)
        return StreamingResponse(buf, media_type="audio/wav",
                                 headers={"Cache-Control": "no-cache"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(500, f"TTS generation failed: {e}")


@router.get("/tts/voices")
async def list_voices():
    return {
        "voices": [{"id": k, "label": v} for k, v in KOKORO_VOICES.items()],
        "kokoro_ready": _pipeline is not None,
    }
