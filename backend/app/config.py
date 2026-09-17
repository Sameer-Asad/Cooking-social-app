"""
Central settings object. Every other module imports `settings` from here
instead of calling os.getenv() directly — this is what makes the
Whisper/Groq model swap a one-line .env change (Technical PRD Sec 3.1).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # STT
    whisper_model: str = "small"

    # Neon Postgres
    database_url: str = ""
    database_url_sync: str = ""

    # CloudAMQP
    celery_broker_url: str = ""

    # Upstash Redis
    upstash_redis_url: str = ""

    # Qdrant Cloud
    qdrant_url: str = ""
    qdrant_api_key: str = ""

    # Auth
    jwt_secret: str = "change-me"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 30
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_redirect_uri: str = ""

    # Observability
    langsmith_tracing: bool = True
    langsmith_api_key: str = ""
    langsmith_project: str = "recipe-bot"

    # Media
    media_root: str = "/app/media"

    # Web search tool
    web_search_provider: str = "duckduckgo"

    # Cookie security
    cookie_secure: bool = False

    # Rate limits
    free_questions_per_day: int = 40
    paid_questions_per_day: int = 100
    free_groq_tokens_per_day: int = 50_000
    paid_groq_tokens_per_day: int = 150_000
    free_tts_per_day: int = 30
    paid_tts_per_day: int = 100
    ip_requests_per_min: int = 30
    app_wide_groq_rpm_guard: int = 25

    # Conversation management
    max_messages_per_session: int = 20
    session_inactivity_timeout_min: int = 30

    # Billing — Lemon Squeezy (merchant-of-record, no dev-side integration
    # fee; only their per-transaction cut applies once a real charge
    # happens). All four must be set in .env before checkout will work —
    # see routes_billing.py for the clear error raised otherwise.
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_pro_variant_id: str = ""
    lemonsqueezy_webhook_secret: str = ""
    # Where Lemon Squeezy's hosted checkout redirects back to after payment.
    frontend_base_url: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
