import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models import ProviderId, RuntimeConfig


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_TAVILY_API_URL = "https://api.tavily.com"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write-test-{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


@lru_cache
def application_home() -> Path:
    if is_frozen():
        executable_dir = Path(sys.executable).resolve().parent
        local_app_data = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")
        )
        candidates = (
            local_app_data / "AgentChat",
            executable_dir / "AgentChatData",
            Path(tempfile.gettempdir()) / "AgentChat",
        )
        for candidate in candidates:
            if _is_writable_directory(candidate):
                return candidate
        raise RuntimeError("找不到可写的数据目录")
    return BACKEND_DIR


def environment_files() -> tuple[Path, ...]:
    if is_frozen():
        executable_dir = Path(sys.executable).resolve().parent
        return (executable_dir / ".env", application_home() / ".env")
    return (BACKEND_DIR / ".env",)


class Settings(BaseSettings):
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    deepseek_api_key: str | None = None
    tavily_api_key: str | None = None
    tavily_api_url: str = DEFAULT_TAVILY_API_URL
    database_url: str = (
        "postgresql+asyncpg://agent:agent@127.0.0.1:5433/agent_chat"
    )
    redis_url: str = "redis://127.0.0.1:6380/0"
    jwt_secret: str = "local-dev-jwt-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "agent-chat"
    jwt_expiration_minutes: int = Field(default=60, ge=5, le=1440)
    login_rate_limit: int = Field(default=5, ge=1, le=100)
    login_rate_window_seconds: int = Field(default=600, ge=60)
    agent_max_steps: int = Field(default=6, ge=1, le=12)
    agent_cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:18080,http://127.0.0.1:18080"
    )

    model_config = SettingsConfigDict(
        env_file=environment_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def live_mode(self) -> bool:
        return bool(
            (self.openai_api_key and self.openai_api_key.strip())
            or (self.deepseek_api_key and self.deepseek_api_key.strip())
        )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.agent_cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def provider_name(self) -> str:
        if self.openai_api_key and self.openai_api_key.strip():
            return self.openai_model
        if self.deepseek_api_key and self.deepseek_api_key.strip():
            return DEEPSEEK_MODEL
        return "demo"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_runtime_config(
    runtime: RuntimeConfig,
    settings: Settings,
) -> RuntimeConfig:
    provider: ProviderId = runtime.provider
    api_key = _clean(runtime.api_key)
    base_url = _clean(runtime.base_url)
    model = _clean(runtime.model)

    if provider == "openai":
        api_key = api_key or _clean(settings.openai_api_key)
        base_url = base_url or settings.openai_base_url
        model = model or settings.openai_model
    elif provider == "deepseek":
        api_key = api_key or _clean(settings.deepseek_api_key)
        base_url = base_url or DEEPSEEK_BASE_URL
        model = model or DEEPSEEK_MODEL
    elif provider == "custom":
        if not base_url:
            raise ValueError("请填写自定义服务的 API 地址")
        if not model:
            raise ValueError("请填写自定义服务的模型名称")

    if provider != "demo":
        if not api_key:
            raise ValueError("请填写所选服务商的 API Key")
        base_url = _validate_http_url(base_url or "", "API 地址")

    web_search_enabled = runtime.web_search_enabled
    tavily_api_key = _clean(runtime.tavily_api_key) or _clean(
        settings.tavily_api_key
    )
    tavily_api_url = (
        _clean(runtime.tavily_api_url)
        or settings.tavily_api_url
        or DEFAULT_TAVILY_API_URL
    )
    if web_search_enabled:
        if not tavily_api_key:
            raise ValueError("启用联网搜索后必须填写 Tavily API Key")
        tavily_api_url = _validate_http_url(
            tavily_api_url,
            "Tavily API 地址",
        )

    return RuntimeConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        web_search_enabled=web_search_enabled,
        tavily_api_key=tavily_api_key,
        tavily_api_url=tavily_api_url,
    )


def _clean(value: str | None) -> str | None:
    cleaned = value.strip() if value else ""
    return cleaned or None


def _validate_http_url(value: str, label: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label}必须是有效的 http 或 https 地址")
    return value.rstrip("/")

