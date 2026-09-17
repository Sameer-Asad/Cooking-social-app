"""
Prometheus + Grafana metrics (Sec 5). Deliberately low-cardinality —
never `user_id` as a label (cardinality explosion risk).
"""

from prometheus_client import Counter, Histogram

request_latency_seconds = Histogram(
    "request_latency_seconds",
    "End-to-end request latency",
    ["endpoint"],
)

cache_hits_total = Counter("cache_hits_total", "Cache hits", ["cache_name"])
cache_misses_total = Counter("cache_misses_total", "Cache misses", ["cache_name"])

queue_depth = Histogram("queue_depth", "Celery queue depth sample", ["queue_name"])

inference_tokens_total = Counter(
    "inference_tokens_total", "Groq tokens consumed", ["model", "direction"]
)

tts_requests_total = Counter("tts_requests_total", "gTTS synthesis attempts")
tts_failures_total = Counter("tts_failures_total", "gTTS synthesis failures")

circuit_breaker_trips_total = Counter(
    "circuit_breaker_trips_total", "Circuit breaker trips", ["breaker_name"]
)
