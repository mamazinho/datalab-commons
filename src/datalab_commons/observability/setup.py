from collections.abc import Sequence
from typing import Any

import logfire
from fastapi import FastAPI

from datalab_commons.observability.logging import get_logger, setup_logging
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
        # Todo serviço aceita traceparent de entrada: é o que costura o browser, esta API e a
        # core-api num trace só. Na API pública isso deixa um estranho pendurar a requisição dele
        # numa árvore escolhida — polui, não vaza.
        distributed_tracing=True,
        sampling=logfire.SamplingOptions.level_or_duration(head=settings.trace_sample_rate),
        scrubbing=logfire.ScrubbingOptions(extra_patterns=SCRUBBING_EXTRA_PATTERNS),
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
    excluded = list(excluded_urls) if excluded_urls else []
    app.add_middleware(RequestLoggingMiddleware, excluded_paths=excluded)
    # Depois do add_middleware de propósito: o span do request precisa envolver o middleware,
    # senão não há trace_id para pôr no header nem para o log de conclusão.
    logfire.instrument_fastapi(app, excluded_urls=excluded or None)

    if engine is not None:
        # O opentelemetry-instrumentation-sqlalchemy declara `sqlalchemy < 2.1.0` e, sem o
        # skip, pula a instrumentação em silêncio — ficaríamos sem span de query no 2.1. O teto
        # é conservador: os eventos de engine que ele usa seguem existindo.
        logfire.instrument_sqlalchemy(engine, skip_dep_check=True)


def instrument_mcp() -> None:
    # A integração de MCP do logfire importa `mcp.shared.session`, removido no mcp 2.x. Perder os
    # spans de MCP é aceitável; derrubar o boot da aplicação por causa deles não é.
    try:
        logfire.instrument_mcp()
    except ModuleNotFoundError:
        get_logger(__name__).warning("Skipped MCP instrumentation: incompatible mcp package layout")


def instrument_agents(settings: ObservabilitySettings | None = None) -> None:
    settings = settings or ObservabilitySettings()
    logfire.instrument_pydantic_ai(include_content=settings.capture_ai_content)
    instrument_mcp()
