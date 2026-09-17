"""
AC-1: detect the question's language and reply in the same language.
Voice input's language comes from Whisper (stt.py); typed text uses
langdetect, a lightweight port of Google's language-detection library.
"""

from langdetect import DetectorFactory, LangDetectException, detect_langs

# Deterministic results — langdetect's detector is seeded randomly by
# default, which makes short strings flip-flop between runs.
DetectorFactory.seed = 0


def detect_text_language(text: str) -> tuple[str, float]:
    """Returns (ISO 639-1 language code, confidence 0-1).

    Edge case (Problem PRD Sec 4): mixed-language input — langdetect
    returns its best-guess dominant language; if confidence is low we
    surface that to the caller so the bot can ask which language to
    reply in instead of guessing silently.
    """
    try:
        candidates = detect_langs(text)
        top = candidates[0]
        return top.lang, top.prob
    except LangDetectException:
        return "en", 0.0


LOW_CONFIDENCE_THRESHOLD = 0.60


def is_ambiguous(confidence: float) -> bool:
    return confidence < LOW_CONFIDENCE_THRESHOLD
