"""
gTTS reliability layers, in the order specified in Sec 9:
  1. Cache first, always (Upstash Redis, keyed on a hash of the text).
  2. Retry with exponential backoff on failure.
  3. Circuit breaker: after 3 consecutive failures, open the circuit and
     fall back to text-only (matches AC-4's graceful-degradation intent).
  4. Throttle outbound calls (~1/sec) — self-limit against an undocumented
     Google-side block, since gTTS has no published rate limits.
  5. Success/failure rate is tracked in Prometheus (observability/metrics.py).

Language validation: an unsupported `lang` raises gTTS's plain ValueError
at construction time (before any network call) — it is NOT a gTTSError,
so it must not go through the retry/circuit-breaker path built for
transient service failures. `_resolve_lang` checks the code against
gTTS's supported set up front and falls back to `_DEFAULT_LANG`, and the
synth loop still catches ValueError separately as a non-retryable guard
in case that set changes between calls.

MARKDOWN: the LLM's reply is Markdown (bold, tables, headers, etc.) meant
for on-screen display — gTTS has no idea what Markdown is and reads the
literal symbols aloud ("asterisk asterisk", "pipe"). `_strip_markdown`
runs on the text right before synthesis (display/caching of the raw
Markdown elsewhere is untouched — only the audio path is cleaned).
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
import time

from gtts import gTTS
from gtts.lang import tts_langs
from gtts.tts import gTTSError
from redis.asyncio import Redis
from langsmith import traceable

from app.observability.metrics import (
    cache_hits_total,
    cache_misses_total,
    circuit_breaker_trips_total,
    tts_failures_total,
    tts_requests_total,
)

_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60
_THROTTLE_SECONDS = 1.0  # ~1 call/sec max, per Sec 9 point 4
_DEFAULT_LANG = (
    "en"  # fallback when the requested/detected lang isn't in gTTS's supported set
)
_CACHE_NAME = "tts_audio"  # label value for cache_hits_total/cache_misses_total

_circuit_open_until: float = 0.0
_consecutive_failures = 0
_last_call_ts: float = 0.0
_throttle_lock = asyncio.Lock()

_SUPPORTED_LANGS: set[str] | None = None  # lazy-loaded, gTTS hits network on first call


class TTSUnavailable(Exception):
    """Raised when the circuit breaker is open, or synthesis fails for a
    non-retryable reason — caller should fall back to a text-only
    response rather than blocking or erroring the request."""


# Order matters: table rows/pipes and headers are stripped structurally
# first (before the generic bold/italic pass would otherwise leave their
# surrounding "|"/"#" characters behind as stray symbols).
_TABLE_SEPARATOR_ROW = re.compile(
    r"^\s*\|?[\s:|-]+\|?\s*$", re.MULTILINE
)  # a |---|---| row
_TABLE_PIPES = re.compile(r"\s*\|\s*")
_HEADER_HASHES = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BOLD_ITALIC = re.compile(r"(\*\*\*|___)(.+?)\1")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1")
_ITALIC = re.compile(r"(\*|_)(.+?)\1")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^\s*>\s?", re.MULTILINE)
_EXTRA_WHITESPACE = re.compile(r"[ \t]{2,}")
_BLANK_LINES = re.compile(r"\n{3,}")


def _strip_markdown(text: str) -> str:
    """Best-effort plain-text version of a Markdown reply, for TTS only.
    Not a full Markdown parser — just removes the symbols gTTS would
    otherwise read aloud (**, *, _, #, |, `, [text](url), >, list
    bullets), while keeping the actual words intact."""
    result = _TABLE_SEPARATOR_ROW.sub("", text)
    result = _TABLE_PIPES.sub(", ", result)
    result = _HEADER_HASHES.sub("", result)
    result = _BOLD_ITALIC.sub(r"\2", result)
    result = _BOLD.sub(r"\2", result)
    result = _ITALIC.sub(r"\2", result)
    result = _INLINE_CODE.sub(r"\1", result)
    result = _LINK.sub(r"\1", result)
    result = _BULLET.sub("", result)
    result = _BLOCKQUOTE.sub("", result)
    result = _EXTRA_WHITESPACE.sub(" ", result)
    result = _BLANK_LINES.sub("\n\n", result)
    return result.strip()


def _resolve_lang(lang: str) -> str:
    """Returns `lang` if gTTS supports it, else `_DEFAULT_LANG`. Loads
    gTTS's supported-language set lazily and caches it for the process
    lifetime — it doesn't change at runtime."""
    global _SUPPORTED_LANGS
    if _SUPPORTED_LANGS is None:
        try:
            _SUPPORTED_LANGS = set(tts_langs().keys())
        except Exception:
            # If even fetching the supported-language list fails (e.g. no
            # network yet), don't block synthesis on it — let the actual
            # gTTS call be the source of truth and fall through to the
            # ValueError guard in the synth loop below.
            return lang
    return lang if lang in _SUPPORTED_LANGS else _DEFAULT_LANG


def _cache_key(text: str, lang: str) -> str:
    digest = hashlib.sha256(f"{lang}:{text}".encode("utf-8")).hexdigest()
    return f"tts:audio:{digest}"


async def _throttle() -> None:
    global _last_call_ts
    async with _throttle_lock:
        now = time.monotonic()
        wait = _THROTTLE_SECONDS - (now - _last_call_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_ts = time.monotonic()


def _synthesize_sync(text: str, lang: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text=text, lang=lang).write_to_fp(buf)
    return buf.getvalue()


@traceable(name="gtts_synthesize")
async def synthesize(redis: Redis, text: str, lang: str) -> bytes:
    """Returns MP3 bytes for `text` in `lang`, or raises TTSUnavailable if
    the circuit breaker is open or the language can't be synthesized at
    all (caller then serves text-only, per AC-4).

    `text` is expected to be the raw Markdown reply as shown on screen —
    it's cleaned via `_strip_markdown` here, right before synthesis, so
    the cache key and the audio itself are both based on the spoken
    (symbol-free) version rather than the literal Markdown."""
    global _consecutive_failures, _circuit_open_until

    now = time.monotonic()
    if now < _circuit_open_until:
        raise TTSUnavailable("gTTS circuit open — falling back to text-only")

    lang = _resolve_lang(lang)
    spoken_text = _strip_markdown(text)

    cache_key = _cache_key(spoken_text, lang)
    cached = await redis.get(cache_key)
    if cached is not None:
        cache_hits_total.labels(cache_name=_CACHE_NAME).inc()
        return cached
    cache_misses_total.labels(cache_name=_CACHE_NAME).inc()

    tts_requests_total.inc()
    loop = asyncio.get_running_loop()

    backoff = 1.0
    last_exc: Exception | None = None
    for attempt in range(3):
        await _throttle()
        try:
            audio_bytes = await loop.run_in_executor(
                None, _synthesize_sync, spoken_text, lang
            )
            _consecutive_failures = 0
            # Recipe responses repeat often — cache for a week.
            await redis.set(cache_key, audio_bytes, ex=60 * 60 * 24 * 7)
            return audio_bytes
        except gTTSError as exc:
            last_exc = exc
            tts_failures_total.inc()
            _consecutive_failures += 1
            if attempt < 2:
                await asyncio.sleep(backoff)
                backoff *= 2
        except ValueError as exc:
            # Non-retryable: an unsupported language code won't become
            # valid by waiting and trying again. Don't count this toward
            # the circuit breaker either — it's a bad input, not evidence
            # the TTS *service* is unhealthy.
            tts_failures_total.inc()
            raise TTSUnavailable(f"gTTS rejected lang={lang!r}: {exc}") from exc

    if _consecutive_failures >= _CIRCUIT_FAILURE_THRESHOLD:
        _circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN_SECONDS
        circuit_breaker_trips_total.labels(breaker_name="gtts").inc()

    raise TTSUnavailable(f"gTTS failed after retries: {last_exc}")
