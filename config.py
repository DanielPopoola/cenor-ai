from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"

    database_url: str = "sqlite:///./cerno.db"
    db_pool_max_size: int = 5
    db_pool_max_overflow: int = 5
    db_pool_recycle_seconds: int = 1800  # max connection lifetime

    cookie_signing_secret: str = "dev-only-insecure-secret-change-me"
    cookie_name: str = "cerno_session"
    cookie_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    oauth_state_ttl_seconds: int = 300

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_request_timeout_seconds: int = 30
    llm_max_completion_tokens: int | None = 4096

    observer_prompt_variant: Literal["zero_shot", "few_shot"] = "zero_shot"

    github_api_token: str = ""

    cv_upload_max_bytes: int = 5 * 1024 * 1024

    session_length_options: list[int] = [15, 30, 40]
    session_length_min: int = 15
    session_length_max: int = 40
    session_length_default: int = 30

    rate_limit_default_per_minute: int = 60
    rate_limit_auth_per_minute: int = 10
    rate_limit_session_create_per_minute: int = 5

    prompt_sanitize_max_chars: int = 10_000
    max_retry_attempts: int = 3

    log_level: str = "INFO"

    @model_validator(mode="after")
    def apply_mode_defaults(self) -> "Settings":
        if self.env == "test":
            self.database_url = "sqlite:///:memory:"

        if self.is_production:
            insecure_defaults = {
                "cookie_signing_secret": "dev-only-insecure-secret-change-me",
            }
            for field, bad_value in insecure_defaults.items():
                if getattr(self, field) == bad_value:
                    raise ValueError(
                        f"Refusing to start in production with default '{field}'. Set it via environment variable."
                    )
            if not self.google_client_id or not self.google_client_secret:
                raise ValueError(
                    "google_client_id/google_client_secret must be set in production."
                )
        return self

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def is_test(self) -> bool:
        return self.env == "test"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
