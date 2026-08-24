from pydantic_settings import BaseSettings, SettingsConfigDict

PYDANTIC_AI_SCOPE = "pydantic-ai"


class ObservabilitySettings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"

    grafana_otlp_endpoint: str = ""
    grafana_otlp_headers: str = ""
    # O conteúdo das conversas sai todo deste scope e responde por quase todos os bytes.
    # Barrado aqui, fica só no Logfire.
    grafana_excluded_scopes: set[str] = {PYDANTIC_AI_SCOPE}

    console_spans: bool = True
    capture_ai_content: bool = True
    trace_sample_rate: float = 1.0
    # Só quem recebe tráfego interno aceita traceparent de entrada; numa API pública qualquer
    # cliente poderia injetar trace_id.
    distributed_tracing: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def otlp_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for pair in self.grafana_otlp_headers.split(","):
            key, separator, value = pair.partition("=")
            if separator:
                headers[key.strip()] = value.strip()
        return headers
