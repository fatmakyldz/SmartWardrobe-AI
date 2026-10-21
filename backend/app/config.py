from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres in production (Neon); SQLite works for local runs and tests.
    database_url: str = "sqlite:///./smartwardrobe.db"

    # Signs access tokens. MUST be set to a long random value in production.
    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    # Web: the refresh token lives in an httpOnly cookie on the API host (api.fomertech.com, same site
    # as the web app). Off only for plain-http local runs.
    refresh_cookie_secure: bool = True

    # Transactional email (verification, password reset) through Resend. Without a key the fake
    # backend logs the message instead (local runs, tests).
    resend_api_key: str = ""
    email_from: str = "SmartWardrobe <noreply@fomertech.com>"
    # Where links in emails point: the web app, which also hands off to the mobile app.
    app_url: str = "https://wardrobe.fomertech.com"
    app_scheme: str = "smartwardrobe"

    # AI providers. Which models run for which feature is in app/ai/routes.default.json.
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Optional override of the routes config: inline JSON or a path to a JSON file.
    ai_routes: str = ""
    # Print full prompts to stderr. Local only: refused at startup unless the database is SQLite.
    ai_debug_log: bool = False

    # Image storage: "db" keeps images in Postgres (local runs and tests);
    # "s3" is a private S3-compatible bucket (Cloudflare R2) — production.
    storage_backend: str = "db"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"
    # Lifetime of the presigned image links the API hands out (and their Cache-Control max-age).
    image_url_seconds: int = 900

    # Error tracking (Sentry). Empty DSN = off (local runs, tests). Events carry no request bodies,
    # no user e-mail: the pseudonymous user id only.
    sentry_dsn: str = ""
    sentry_environment: str = "production"
    sentry_traces_sample_rate: float = 0.0  # performance tracing off; errors only

    # Public URL of this API, used to build image links in db storage mode.
    public_base_url: str = ""

    # Comma-separated origins for the web app (credentials allowed). Empty = any origin, which is only
    # accepted with a local SQLite database; with Postgres the API refuses to start.
    cors_origins: str = ""

    # Proxies whose X-Forwarded-For / X-Forwarded-Proto we believe (IPs or CIDRs, comma-separated).
    # Default: loopback + private ranges, where the Hugging Face Space load balancer connects from.
    # Empty = loopback only. Never "*": anyone could then fake their IP and skip the rate limits.
    trusted_proxy_hosts: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    # Also trust Cloudflare's published ranges (app/cloudflare_ips.txt): set when requests come
    # through the api.fomertech.com Worker, so its X-Forwarded-For carries the visitor's IP.
    cloudflare_proxy: bool = False

    # Per-user limits on the paid-by-quota LLM endpoints.
    analyze_limit: str = "30/hour"
    suggest_limit: str = "20/hour"
    demo_limit: str = "10/hour"
    # Auth endpoints (per IP; resend-verification per user).
    refresh_limit: str = "60/hour"
    forgot_limit: str = "5/hour"
    reset_limit: str = "10/hour"
    verify_limit: str = "20/hour"
    resend_verification_limit: str = "5/hour"

    demo_ttl_hours: int = 24
    max_upload_mb: int = 10

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_list(self) -> list[str]:
        hosts = [h.strip() for h in self.trusted_proxy_hosts.split(",") if h.strip()]
        hosts = hosts or ["127.0.0.1", "::1"]
        if self.cloudflare_proxy:
            hosts += cloudflare_ranges()
        return hosts


CLOUDFLARE_IPS_FILE = Path(__file__).with_name("cloudflare_ips.txt")


def cloudflare_ranges() -> list[str]:
    lines = (line.strip() for line in CLOUDFLARE_IPS_FILE.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
