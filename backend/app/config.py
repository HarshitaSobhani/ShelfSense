from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SHELFSENSE_", extra="ignore")

    database_url: str = "postgresql+psycopg://shelfsense:shelfsense@localhost:5432/shelfsense"
    secret_key: str = Field(default="dev-insecure-change-me", min_length=16)
    environment: str = "development"  # development | production | test
    session_days: int = 7
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173"
    admin_emails: str = ""  # comma-separated; matching accounts become admins on registration

    # embeddings
    embedding_provider: str = "sentence-transformers"  # sentence-transformers | none
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_revision: str = "main"
    embedding_dim: int = 384
    embedding_schema_version: int = 1  # bump when the document template changes
    hybrid_lexical_weight: float = 0.05  # share of keyword score in hybrid search (rest is semantic)
    search_relative_cutoff: float = 0.5  # drop semantic/hybrid hits scoring below this fraction of the best hit
    min_semantic_score: float = 0.15  # cosine floor for search candidates; tune with `python -m app.cli evaluate`

    # open library
    openlibrary_base_url: str = "https://openlibrary.org"
    openlibrary_covers_url: str = "https://covers.openlibrary.org"
    openlibrary_contact: str = "set-SHELFSENSE_OPENLIBRARY_CONTACT@example.invalid"
    openlibrary_timeout: float = 10.0

    # limits
    max_body_bytes: int = 64 * 1024
    rate_limit_per_minute: int = 240
    auth_rate_limit_per_minute: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.environment == "production" and s.secret_key.startswith(("dev-insecure", "replace-with")):
        raise RuntimeError("SHELFSENSE_SECRET_KEY must be set to a random value in production")
    return s
