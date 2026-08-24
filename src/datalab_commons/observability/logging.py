import logging
from typing import Any

from opentelemetry._logs import LoggerProvider
from opentelemetry.baggage import get_all as get_baggage
from opentelemetry.instrumentation.logging.handler import LoggingHandler

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Bibliotecas que já são instrumentadas e viram span: o log de INFO delas só duplicaria em texto.
QUIET_LOGGERS = ("httpx", "httpcore")

LOG_CALL_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel", "extra"})

CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


class BaggageFilter(logging.Filter):
    """O OpenTelemetry cola Baggage em span automaticamente, mas não em log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in get_baggage().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class StructuredLogger(logging.LoggerAdapter):
    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        fields = {key: kwargs.pop(key) for key in list(kwargs) if key not in LOG_CALL_KWARGS}
        kwargs["extra"] = {**(kwargs.get("extra") or {}), **fields}
        return msg, kwargs


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(logging.getLogger(name), {})


def setup_logging(level: str | int, logger_provider: LoggerProvider | None = None) -> None:
    """Sem `force=True` o `basicConfig` é no-op: o uvicorn já instalou um handler no root."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if logger_provider is not None:
        otel_handler = LoggingHandler(
            level=logging.NOTSET,
            logger_provider=logger_provider,
            log_code_attributes=True,
        )
        # Sem isto o corpo do log exportado sai formatado ("INFO:modulo:mensagem"); o nível e o
        # logger já viajam como campos próprios, e o Loki quer só a mensagem.
        otel_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(otel_handler)

    for handler in handlers:
        handler.addFilter(BaggageFilter())

    logging.basicConfig(level=level, format=CONSOLE_FORMAT, handlers=handlers, force=True)

    # O uvicorn desliga o propagate destes; sem religar, "Application startup complete" não sai.
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
