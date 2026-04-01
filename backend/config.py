"""Centralized application configuration for ChaosAgent backend."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings used across backend modules."""

    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:8000/auth/google/callback",
        alias="GOOGLE_REDIRECT_URI",
    )
    jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
    jwt_expire_days: int = Field(default=7, alias="JWT_EXPIRE_DAYS")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    openpipe_api_key: str = Field(default="", alias="OPENPIPE_API_KEY")
    langchain_tracing_v2: bool = Field(default=True, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="chaos-agent", alias="LANGCHAIN_PROJECT")
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    redis_checkpoint_ttl_hours: int = Field(default=24, alias="REDIS_CHECKPOINT_TTL_HOURS")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:chaos123@localhost:5432/chaosagent",
        alias="DATABASE_URL",
    )
    streamlit_url: str = Field(default="http://localhost:8501", alias="STREAMLIT_URL")
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    use_memory_saver: bool = Field(default=True, alias="USE_MEMORY_SAVER")
    dev_bypass_auth: bool = Field(default=True, alias="DEV_BYPASS_AUTH")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    extra_cors_origins: str = Field(default="", alias="EXTRA_CORS_ORIGINS")

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()

