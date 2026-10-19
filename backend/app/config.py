from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres in production (Neon); SQLite works for local runs and tests.
    database_url: str = "sqlite:///./smartwardrobe.db"

    # Signs login tokens. MUST be set to a long random value in production.
    secret_key: str = "dev-only-change-me"
    token_days: int = 30

    # Groq (OpenAI-compatible API)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_text_model: str = "openai/gpt-oss-120b"
    groq_vision_model: str = "qwen/qwen3.8-27b"

    # Image storage: "db" keeps images in Postgres (zero setup);
    # "s3" uses any S3-compatible bucket (Cloudflare R2, Supabase Storage…).
    storage_backend: str = "db"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""  # e.g. https://images.fomertech.com
    s3_region: str = "auto"

    # Public URL of this API, used to build image links in db storage mode.
    public_base_url: str = ""

    # Comma-separated origins for the web app. Empty = allow all (local dev).
    cors_origins: str = ""

    # Proxies whose X-Forwarded-For / X-Forwarded-Proto we believe (IPs or CIDRs, comma-separated).
    # Default: loopback + private ranges, where the Hugging Face Space load balancer connects from.
    # Empty = loopback only. Never "*": anyone could then fake their IP and skip the rate limits.
    trusted_proxy_hosts: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    # Per-user limits on the paid-by-quota LLM endpoints.
    analyze_limit: str = "30/hour"
    suggest_limit: str = "20/hour"
    demo_limit: str = "10/hour"

    demo_ttl_hours: int = 24
    max_upload_mb: int = 10
    max_items: int = 300  # per user; POST /items answers wardrobe_full beyond this

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_list(self) -> list[str]:
        hosts = [h.strip() for h in self.trusted_proxy_hosts.split(",") if h.strip()]
        return hosts or ["127.0.0.1", "::1"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
