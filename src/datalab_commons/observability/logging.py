import logging
from typing import Any

from opentelemetry._logs import LoggerProvider
from opentelemetry.baggage import get_all as get_baggage
from opentelemetry.instrumentation.logging.handler import LoggingHandler

# O uvicorn desliga o propagate destes; sem religar, "Application startup complete" e os erros de
# boot não saem do processo.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error")

# `uvicorn.access` fica de fora: o log de conclusão do middleware diz o mesmo e mais — rota,
# duração, trace_id e quem fez a requisição.
SILENT_LOGGERS = ("uvicorn.access",)

# Já viram span (httpx) ou registram a própria exportação de telemetria (urllib3, que é o
# transporte do exportador OTLP e em DEBUG loga um POST a cada lote de logs).
QUIET_LOGGERS = ("httpx", "httpcore", "urllib3", "requests")

LOG_CALL_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel", "extra"})

CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# Atributos que todo LogRecord tem. O que sobra veio de `extra` ou do Baggage.
# `color_message` é o mesmo texto com escapes ANSI que o uvicorn manda junto — puro ruído aqui.
STANDARD_RECORD_ATTRIBUTES = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "color_message",
}


class BaggageFilter(logging.Filter):
    """O OpenTelemetry cola Baggage em span automaticamente, mas não em log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_baggage().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class ConsoleFormatter(logging.Formatter):
    """Mostra no terminal os campos que o Logfire receberia, para o log dizer o mesmo nos dois."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        fields = {key: value for key, value in record.__dict__.items() if key not in STANDARD_RECORD_ATTRIBUTES}
        if not fields:
            return line
        return f"{line} | " + " ".join(f"{key}={value}" for key, value in sorted(fields.items()))


class StructuredLogger(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        fields = {key: kwargs.pop(key) for key in list(kwargs) if key not in LOG_CALL_KWARGS}
        kwargs["extra"] = {**(kwargs.get("extra") or {}), **fields}
        return msg, kwargs


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(logging.getLogger(name), {})


def setup_logging(level: str | int, logger_provider: LoggerProvider | None = None) -> None:
    """Sem `force=True` o `basicConfig` é no-op: o uvicorn já instalou um handler no root."""
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleFormatter(CONSOLE_FORMAT))
    handlers: list[logging.Handler] = [console_handler]

    if logger_provider is not None:
        otel_handler = LoggingHandler(
            level=logging.NOTSET,
            logger_provider=logger_provider,
            log_code_attributes=True,
        )
        otel_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(otel_handler)

    for handler in handlers:
        handler.addFilter(BaggageFilter())

    logging.basicConfig(level=level, handlers=handlers, force=True)

    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    for name in SILENT_LOGGERS:
        silent_logger = logging.getLogger(name)
        silent_logger.handlers.clear()
        silent_logger.propagate = False

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
