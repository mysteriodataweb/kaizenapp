"""Configuration centralisée, lue depuis l'environnement (jamais depuis Git)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Convertit une URL Postgres (Neon, Render…) vers le dialecte psycopg 3 de SQLAlchemy."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    # `../.env` / `../.env.local` : variables écrites par `neon deploy` / `neon env pull` à la racine du dépôt ;
    # `backend/.env` (lu en dernier) reste prioritaire. Les variables d'environnement priment toujours.
    model_config = SettingsConfigDict(
        env_file=("../.env", "../.env.local", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Opportunity Intelligence"
    log_level: str = "INFO"

    database_url: str = "postgresql://postgres:postgres@localhost:5432/oi_dev"
    # Connexion directe (sans PgBouncer) pour Alembic ; Neon la fournit sous le nom DATABASE_URL_UNPOOLED.
    database_migration_url: str | None = Field(
        default=None, validation_alias=AliasChoices("DATABASE_MIGRATION_URL", "DATABASE_URL_UNPOOLED")
    )
    db_pool_size: int = 5
    db_max_overflow: int = 5

    secret_key: str = Field(default="", repr=False)
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    default_timezone: str = "Europe/Paris"
    session_ttl_hours: int = 24 * 14
    password_reset_ttl_minutes: int = 30

    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = Field(default=None, repr=False)

    # Inscription publique (désactivée par défaut) : adresse e-mail confirmée obligatoire avant la connexion.
    allow_registration: bool = False
    email_verification_ttl_hours: int = 48
    registration_max_per_ip_per_hour: int = 5
    registration_max_per_hour: int = 30

    resend_api_key: str | None = Field(default=None, repr=False)
    email_from: str | None = None
    alert_recipient: str | None = None
    email_allowed_recipients: str = ""

    ai_provider: str | None = None
    ai_api_key: str | None = Field(default=None, repr=False)
    ai_model: str | None = None

    storage_provider: Literal["local", "s3", "none"] = "local"
    storage_local_dir: str = "./storage"
    storage_bucket: str | None = None
    storage_endpoint_url: str | None = None
    storage_region: str = "auto"
    storage_access_key: str | None = Field(default=None, repr=False)
    storage_secret_key: str | None = Field(default=None, repr=False)
    max_upload_mb: int = 4

    collector_user_agent: str = "OpportunityIntelligence/1.0 (+https://github.com/mysteriodataweb/kaizenapp)"
    collector_timeout_seconds: float = 20.0
    admin_collect_cooldown_minutes: int = 10

    # Pondération du matching (somme libre, normalisée à l'exécution)
    match_weight_academic: float = 30
    match_weight_skills: float = 25
    match_weight_funding: float = 20
    match_weight_preferences: float = 15
    match_weight_languages: float = 10

    @field_validator("database_url", "database_migration_url")
    @classmethod
    def _normalize_db(cls, v: str | None) -> str | None:
        return normalize_database_url(v) if v else v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def email_enabled(self) -> bool:
        return bool(self.resend_api_key and self.email_from)

    @property
    def registration_open(self) -> bool:
        # En production, sans e-mail réel, personne ne pourrait confirmer son adresse : inscriptions fermées.
        return self.allow_registration and (self.email_enabled or not self.is_production)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_provider and self.ai_api_key)

    @property
    def allowed_recipients(self) -> set[str]:
        extra = {e.strip().lower() for e in self.email_allowed_recipients.split(",") if e.strip()}
        if self.alert_recipient:
            extra.add(self.alert_recipient.strip().lower())
        return extra

    @property
    def match_weights(self) -> dict[str, float]:
        return {
            "academic": self.match_weight_academic,
            "skills": self.match_weight_skills,
            "funding": self.match_weight_funding,
            "preferences": self.match_weight_preferences,
            "languages": self.match_weight_languages,
        }

    def check_production_ready(self) -> list[str]:
        """Retourne les problèmes bloquants de configuration en production."""
        problems: list[str] = []
        if self.is_production:
            if len(self.secret_key) < 32:
                problems.append("SECRET_KEY absente ou trop courte (>= 32 caractères requis)")
            if "localhost" in self.database_url:
                problems.append("DATABASE_URL pointe vers localhost en production")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
