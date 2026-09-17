"""
Whisper wrapper (openai-whisper). Model size comes from Settings.whisper_model
(env-driven — Sec 3.1) and is loaded once at startup, not per request.

Whisper is CPU/GPU-bound, synchronous code — it must never run inline in an
`async def` handler (Sec 6, FastAPI async discipline). Callers use
`transcribe()` from an async context; it internally hops to a thread via
loop.run_in_executor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import whisper

from app.config import settings
from langsmith import traceable

_model: whisper.Whisper | None = None


def load_model() -> whisper.Whisper:
    """Called once at app startup (see main.py lifespan)."""
    global _model
    if _model is None:
        _model = whisper.load_model(settings.whisper_model)
    return _model


@dataclass
class TranscriptionResult:
    text: str
    detected_language: str
    language_confidence: float


def _transcribe_sync(audio_path: str, language_hint: str | None) -> TranscriptionResult:
    model = load_model()

    # Detect language + confidence first (per Sec 3.1: "surface Whisper's
    # detected-language confidence" so the UI can flag low-confidence audio).
    audio = whisper.load_audio(audio_path)
    audio = whisper.pad_or_trim(audio)
    mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels).to(model.device)
    _, probs = model.detect_language(mel)
    detected_language = max(probs, key=probs.get)
    confidence = probs[detected_language]

    result = model.transcribe(
        audio_path,
        language=language_hint or detected_language,
    )
    return TranscriptionResult(
        text=result["text"].strip(),
        detected_language=detected_language,
        language_confidence=confidence,
    )


@traceable(name="whisper_stt")
async def transcribe(
    audio_path: str, language_hint: str | None = None
) -> TranscriptionResult:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _transcribe_sync, audio_path, language_hint)


# Per Sec 3.1 feasibility results: WER is 0.191 (en) / 0.505 (ur) / 0.705 (hi).
# The manual-edit-before-send step is mandatory for ur/hi, and encouraged
# (not enforced) for anything outside {en, ur, hi} since it's unverified.
VALIDATED_LANGUAGES = {"en", "ur", "hi"}
MANDATORY_EDIT_LANGUAGES = {"ur", "hi"}


def requires_mandatory_edit_step(language_code: str) -> bool:
    return language_code in MANDATORY_EDIT_LANGUAGES


def is_validated_language(language_code: str) -> bool:
    return language_code in VALIDATED_LANGUAGES
