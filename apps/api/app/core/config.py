"""Application configuration loaded from environment variables with defaults.

Every value can be overridden through an environment variable or a local
``.env`` file. The settings are read once and cached; no real secrets are
ever committed — the repository only ships ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AppMode = Literal["mock", "production"]


class Settings(BaseSettings):
    """Runtime settings for the Zhibian API.

    Env lookup is case-insensitive (``APP_MODE`` maps to ``app_mode``).
    ``env_file`` is tried as ``.env`` next to the process and as ``../.env``
    (the monorepo root) so the API works whether it is run from ``apps/api``
    or the repository root.
    """

    model_config = SettingsConfigDict(
        # Relative to the process CWD.  From apps/api this covers:
        #   .env (apps/api), ../.env (apps), ../../.env (repo root)
        # From the repo root it covers: .env and ../.env.
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Application mode -------------------------------------------
    # "mock" lets the app start without any external service or secret.
    app_mode: AppMode = Field(default="mock")

    # ---- Database -----------------------------------------------------
    # PostgreSQL connection string (asyncpg driver).
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/zhibian"
    )

    # ---- Zhihu Open Platform ------------------------------------------
    # Access Secret (production only; keep in env / untracked .env).
    zhihu_access_secret: str = Field(default="")
    # Search endpoint is a controlled config value, never user input.
    zhihu_search_url: str = Field(
        default="https://developer.zhihu.com/api/v1/content/zhihu_search"
    )

    # ---- LLM provider (OpenAI-compatible) ------------------------------
    llm_api_key: str = Field(default="")
    llm_base_url: str = Field(default="")
    llm_model: str = Field(default="")

    # ---- Embedding provider (OpenAI-compatible) -------------------------
    embedding_api_key: str = Field(default="")
    embedding_base_url: str = Field(default="")
    embedding_model: str = Field(default="")

    # ---- Logging / CORS / serving --------------------------------------
    log_level: str = Field(default="INFO")
    cors_origins: str = Field(default="http://localhost:3000")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated ``CORS_ORIGINS`` value into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_mock_mode(self) -> bool:
        """True when the app runs without external services."""
        return self.app_mode == "mock"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()


settings = get_settings()
