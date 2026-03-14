"""Configuration management for Build Triage AI."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API Keys
    anthropic_api_key: str
    github_token: str | None = None

    # Database
    database_url: str | None = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Analysis settings
    confidence_threshold: float = 0.7
    max_log_length: int = 50000
    analysis_timeout: int = 30

    # Claude settings
    claude_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 2000


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
