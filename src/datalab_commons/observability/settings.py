from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilitySettings(BaseSettings):
    environment: str = "development"
    log_level: str = "INFO"

    console_spans: bool = True
    capture_ai_content: bool = True
    trace_sample_rate: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
