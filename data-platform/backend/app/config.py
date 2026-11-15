from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://agent:agent@127.0.0.1:5433/agent_chat"
    redis_url: str = "redis://127.0.0.1:6380/0"
    jwt_secret: str = "local-dev-jwt-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "agent-chat"
    jwt_expiration_minutes: int = Field(default=60, ge=5, le=1440)
    login_rate_limit: int = Field(default=5, ge=1, le=100)
    login_rate_window_seconds: int = Field(default=600, ge=60)
    agent_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:18081,http://127.0.0.1:18081"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.agent_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
