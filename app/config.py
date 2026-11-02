from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vector_backend: Literal["pgvector", "pinecone"] = "pgvector"
    pinecone_key: SecretStr = SecretStr("")
    pinecone_index: str = Field(default="agentic-rag", pattern=r"^[a-z0-9][a-z0-9-]{0,44}$")
    pinecone_namespace: str = "rag-clone"
    database_url: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "openrouter/free"
    allow_paid_models: bool = False
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = Field(default=768, ge=768, le=768)
    cors_origin: str = ""
    web_frontend_url: str = "http://localhost:3001"
    history_exchanges: int = Field(default=4, ge=0, le=4)
    history_max_chars: int = Field(default=6000, ge=0, le=12000)
    upload_timeout_seconds: int = Field(default=1800, ge=1, le=1800)
    request_timeout_seconds: int = Field(default=220, ge=1, le=240)

    @model_validator(mode="after")
    def free_chat_only(self):
        if not self.allow_paid_models and not (
            self.openrouter_model == "openrouter/free" or self.openrouter_model.endswith(":free")
        ):
            raise ValueError("Paid chat models require ALLOW_PAID_MODELS=true")
        return self

    @property
    def embedding_signature(self) -> str:
        return f"openrouter:{self.embedding_model}:{self.embedding_dimensions}"


@lru_cache
def settings() -> Settings:
    return Settings()
