from collections.abc import Sequence
from typing import Any

import logfire
from fastapi import FastAPI

from datalab_commons.observability.exporters import (
    build_grafana_log_processors,
    build_grafana_span_processors,
)
from datalab_commons.observability.logging import setup_logging
from datalab_commons.observability.middleware import RequestLoggingMiddleware
from datalab_commons.observability.settings import ObservabilitySettings

SCRUBBING_EXTRA_PATTERNS = ["x-provider-token", "x-api-key", "x-company-id"]


def configure_observability(service_name: str, service_version: str) -> ObservabilitySettings:
    settings = ObservabilitySettings()

    logfire.configure(
        service_name=service_name,
        service_version=service_version,
        environment=settings.environment,
        send_to_logfire="if-token-present",
        console=logfire.ConsoleOptions() if settings.console_spans else False,
        distributed_tracing=settings.distributed_tracing,
        sampling=logfire.SamplingOptions.level_or_duration(head=settings.trace_sample_rate),
        scrubbing=logfire.ScrubbingOptions(extra_patterns=SCRUBBING_EXTRA_PATTERNS),
        additional_span_processors=build_grafana_span_processors(settings),
        advanced=logfire.AdvancedOptions(log_record_processors=build_grafana_log_processors(settings)),
    )

    setup_logging(settings.log_level, logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_logger_provider())
    logfire.instrument_httpx()

    return settings


def instrument_fastapi_app(
    app: FastAPI,
    *,
    engine: Any = None,
    excluded_urls: Sequence[str] | None = None,
) -> None:
    app.add_middleware(RequestLoggingMiddleware)
    # Depois do add_middleware de propósito: o span do request precisa envolver o middleware,
    # senão não há trace_id para pôr no header nem para o log de conclusão.
    logfire.instrument_fastapi(app, excluded_urls=list(excluded_urls) if excluded_urls else None)

    if engine is not None:
        logfire.instrument_sqlalchemy(engine)


def instrument_mcp() -> None:
    logfire.instrument_mcp()


def instrument_agents(settings: ObservabilitySettings | None = None) -> None:
    settings = settings or ObservabilitySettings()
    # O conteúdo das conversas viaja como atributo dos spans do scope `pydantic-ai`, que o
    # exportador do Grafana barra — por isso ele fica só no Logfire.
    logfire.instrument_pydantic_ai(include_content=settings.capture_ai_content)
    instrument_mcp()
