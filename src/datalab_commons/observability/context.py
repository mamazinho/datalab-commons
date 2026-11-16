from collections.abc import Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType

from opentelemetry.context import Context
from opentelemetry.sdk.trace import Span, SpanProcessor

# Mesmo teto do Baggage do Logfire, que fazia este papel antes.
MAX_FIELD_LENGTH = 1000

_log_fields: ContextVar[Mapping[str, str]] = ContextVar("log_fields", default=MappingProxyType({}))


class LogFields:
    @staticmethod
    def add(**fields: object) -> None:
        values = {key: str(value)[:MAX_FIELD_LENGTH] for key, value in fields.items() if value is not None}
        if values:
            _log_fields.set(MappingProxyType({**_log_fields.get(), **values}))

    @staticmethod
    def current() -> Mapping[str, str]:
        return _log_fields.get()

    @staticmethod
    @contextmanager
    def scope() -> Generator[None]:
        token = _log_fields.set(MappingProxyType({}))
        try:
            yield
        finally:
            _log_fields.reset(token)


class LogFieldsSpanProcessor(SpanProcessor):
    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        attributes = span.attributes or {}
        span.set_attributes({key: value for key, value in LogFields.current().items() if key not in attributes})
