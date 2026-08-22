"""Configuração central (12-factor): tudo vem de variáveis de ambiente / .env com defaults seguros."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do monorepo (…/asclepio) — usada para resolver caminhos relativos (data/, ml/)
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- app ---
    app_name: str = "Asclépio"
    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    api_prefix: str = "/api/v1"

    # --- segurança ---
    secret_key: str = Field(default="dev-only-insecure-secret-key-change-me", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_per_minute: int = 60
    login_rate_limit_per_minute: int = 10
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    password_min_length: int = 10
    max_request_body_bytes: int = 1_000_000

    # --- banco ---
    database_url: str = f"sqlite+aiosqlite:///{REPO_ROOT / 'data' / 'asclepio.sqlite'}"
    seed_on_startup: bool = True

    # --- LLM ---
    llm_provider: Literal["ollama", "litellm", "openai", "fake"] = "ollama"
    llm_model: str = "asclepio-med"
    llm_fallback_model: str = "llama3.1:8b"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 700
    llm_timeout_seconds: int = 120
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    litellm_base_url: str = "http://localhost:4000"
    litellm_api_key: str = "sk-asclepio-dev"

    # --- embeddings / RAG ---
    embeddings_provider: Literal["ollama", "openai", "litellm", "fake"] = "ollama"
    embeddings_model: str = "nomic-embed-text"
    vectorstore_dir: str = str(REPO_ROOT / "data" / "vectorstore")
    knowledge_base_dir: str = str(REPO_ROOT / "data" / "knowledge_base")
    checkpoints_dir: str = str(REPO_ROOT / "data" / "checkpoints")
    synthetic_patients_file: str = str(REPO_ROOT / "data" / "synthetic" / "patients.json")
    ml_registry_file: str = str(REPO_ROOT / "ml" / "registry.json")
    ml_eval_report_file: str = str(REPO_ROOT / "ml" / "reports" / "eval_latest.json")
    rag_top_k: int = 5
    rag_min_score: float = 0.25

    # --- observabilidade ---
    enable_metrics: bool = True
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return ",".join(o.strip() for o in v.split(",") if o.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins.split(",") if self.cors_origins else []

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"

    @property
    def langfuse_active(self) -> bool:
        return bool(self.langfuse_enabled and self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod and s.secret_key.startswith("dev-only"):
        raise RuntimeError("SECRET_KEY padrão não é permitido em produção. Defina SECRET_KEY.")
    return s
