from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"
    redoc_url: str = "/redoc"
    disable_docs: bool = False

    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    proxy_headers: bool = True
    forwarded_allow_ips: str = "*"

    cors_allow_origins: list[str] = []

    @property
    def fastapi_kwargs(self) -> dict[str, Any]:
        if self.disable_docs:
            return {"docs_url": None, "openapi_url": None, "redoc_url": None}
        return {"docs_url": self.docs_url, "openapi_url": self.openapi_url, "redoc_url": self.redoc_url}

    model_config = SettingsConfigDict(env_file=".env", validate_assignment=True, extra="ignore")
