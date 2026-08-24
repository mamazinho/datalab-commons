from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    debug: bool = False
    docs_url: str = "/docs"
    openapi_prefix: str = ""
    openapi_url: str = "/openapi.json"
    redoc_url: str = "/redoc"
    title: str = "FastAPI"
    version: str = "0.1.0"

    # Custom settings
    disable_docs: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    proxy_headers: bool = True
    forwarded_allow_ips: str = "*"

    cors_allow_origins: list[str] = []

    @property
    def fastapi_kwargs(self) -> dict[str, Any]:
        """
        This returns a dictionary of the most commonly used keyword arguments when initializing a FastAPI instance

        If `self.disable_docs` is True, the various docs-related arguments are disabled, preventing your spec from being
        published.
        """
        fastapi_kwargs: dict[str, Any] = {
            "debug": self.debug,
            "docs_url": self.docs_url,
            "openapi_prefix": self.openapi_prefix,
            "openapi_url": self.openapi_url,
            "redoc_url": self.redoc_url,
            "title": self.title,
            "version": self.version,
        }
        if self.disable_docs:
            fastapi_kwargs.update({"docs_url": None, "openapi_url": None, "redoc_url": None})
        return fastapi_kwargs

    model_config = SettingsConfigDict(env_file=".env", validate_assignment=True, extra="ignore")
