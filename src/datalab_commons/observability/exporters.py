from collections.abc import Sequence

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult, SpanProcessor

from datalab_commons.observability.settings import ObservabilitySettings


class ScopeFilteringSpanExporter(SpanExporter):
    """Barra os spans dos scopes da denylist antes de exportar.

    Os spans que sobram carregam o mesmo trace_id, então o Grafana continua levando ao Logfire —
    onde o que foi barrado está inteiro.
    """

    def __init__(self, wrapped: SpanExporter, excluded_scopes: frozenset[str]) -> None:
        self.wrapped = wrapped
        self.excluded_scopes = excluded_scopes

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        kept = [span for span in spans if scope_name(span) not in self.excluded_scopes]
        if not kept:
            return SpanExportResult.SUCCESS
        return self.wrapped.export(kept)

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self.wrapped.force_flush(timeout_millis)

    def shutdown(self) -> None:
        self.wrapped.shutdown()


def scope_name(span: ReadableSpan) -> str:
    scope = span.instrumentation_scope
    return scope.name if scope else ""


def build_grafana_span_processors(settings: ObservabilitySettings) -> list[SpanProcessor]:
    if not settings.grafana_otlp_endpoint:
        return []

    exporter = OTLPSpanExporter(
        endpoint=signal_endpoint(settings.grafana_otlp_endpoint, "traces"),
        headers=settings.otlp_headers,
    )
    return [BatchSpanProcessor(ScopeFilteringSpanExporter(exporter, frozenset(settings.grafana_excluded_scopes)))]


def build_grafana_log_processors(settings: ObservabilitySettings) -> list[LogRecordProcessor]:
    if not settings.grafana_otlp_endpoint:
        return []

    exporter = OTLPLogExporter(
        endpoint=signal_endpoint(settings.grafana_otlp_endpoint, "logs"),
        headers=settings.otlp_headers,
    )
    return [BatchLogRecordProcessor(exporter)]


def signal_endpoint(base_url: str, signal: str) -> str:
    """O exportador HTTP usa o endpoint literalmente; quem anexa `/v1/<sinal>` é só a env var."""
    return f"{base_url.rstrip('/')}/v1/{signal}"
