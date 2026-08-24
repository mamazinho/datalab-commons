from pydantic_settings import BaseSettings, SettingsConfigDict

PYDANTIC_AI_SCOPE = "pydantic-ai"


class ObservabilitySettings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"

    grafana_otlp_endpoint: str = ""
    grafana_otlp_headers: str = ""
    # only Logfire.
    grafana_excluded_scopes: set[str] = {PYDANTIC_AI_SCOPE}

    console_spans: bool = True
    capture_ai_content: bool = True
    trace_sample_rate: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def otlp_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for pair in self.grafana_otlp_headers.split(","):
            key, separator, value = pair.partition("=")
            if separator:
                headers[key.strip()] = value.strip()
        return headers
