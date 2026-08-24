import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.util.instrumentation import InstrumentationScope

from datalab_commons.observability.exporters import (
    ScopeFilteringSpanExporter,
    build_grafana_log_processors,
    build_grafana_span_processors,
    signal_endpoint,
)
from datalab_commons.observability.settings import PYDANTIC_AI_SCOPE, ObservabilitySettings

GRAFANA_ENDPOINT = "https://otlp-gateway-prod.grafana.test/otlp"


class CollectingExporter(SpanExporter):
    def __init__(self) -> None:
        self.exported: list[ReadableSpan] = []
        self.calls = 0
        self.flushed = False
        self.was_shutdown = False

    def export(self, spans):
        self.calls += 1
        self.exported.extend(spans)
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis=30_000):
        self.flushed = True
        return True

    def shutdown(self):
        self.was_shutdown = True


def span_from_scope(scope_name: str | None) -> ReadableSpan:
    scope = InstrumentationScope(scope_name) if scope_name else None
    return ReadableSpan(name=f"span-{scope_name}", instrumentation_scope=scope)


@pytest.fixture
def collector() -> CollectingExporter:
    return CollectingExporter()


@pytest.fixture
def filtering(collector) -> ScopeFilteringSpanExporter:
    return ScopeFilteringSpanExporter(collector, frozenset({PYDANTIC_AI_SCOPE}))


class TestScopeFiltering:
    """O que passa por aqui é o que vira custo no Grafana. Se o filtro parar de barrar o scope
    das conversas, a fatura cresce em silêncio — nada mais no sistema reclama."""

    def test_barra_os_spans_do_scope_das_conversas(self, filtering, collector):
        filtering.export([span_from_scope(PYDANTIC_AI_SCOPE)])

        assert collector.exported == []

    def test_deixa_passar_os_demais_scopes(self, filtering, collector):
        filtering.export([span_from_scope("opentelemetry.instrumentation.fastapi")])

        assert [span.name for span in collector.exported] == ["span-opentelemetry.instrumentation.fastapi"]

    def test_separa_o_barrado_do_permitido_no_mesmo_lote(self, filtering, collector):
        filtering.export([span_from_scope(PYDANTIC_AI_SCOPE), span_from_scope("logfire")])

        assert [span.name for span in collector.exported] == ["span-logfire"]

    def test_nao_chama_o_exportador_quando_o_lote_inteiro_e_barrado(self, filtering, collector):
        result = filtering.export([span_from_scope(PYDANTIC_AI_SCOPE)])

        assert collector.calls == 0
        assert result is SpanExportResult.SUCCESS

    def test_trata_span_sem_scope_como_permitido(self, filtering, collector):
        filtering.export([span_from_scope(None)])

        assert len(collector.exported) == 1

    @pytest.mark.parametrize(
        ("action", "flag"),
        [
            pytest.param("force_flush", "flushed", id="force-flush"),
            pytest.param("shutdown", "was_shutdown", id="shutdown"),
        ],
    )
    def test_repassa_o_ciclo_de_vida_ao_exportador_embrulhado(self, filtering, collector, action, flag):
        getattr(filtering, action)()

        assert getattr(collector, flag) is True


class TestGrafanaProcessors:
    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(build_grafana_span_processors, id="spans"),
            pytest.param(build_grafana_log_processors, id="logs"),
        ],
    )
    def test_sem_endpoint_configurado_nao_cria_processador(self, build):
        assert build(ObservabilitySettings(grafana_otlp_endpoint="")) == []

    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(build_grafana_span_processors, id="spans"),
            pytest.param(build_grafana_log_processors, id="logs"),
        ],
    )
    def test_com_endpoint_configurado_cria_um_processador(self, build):
        assert len(build(ObservabilitySettings(grafana_otlp_endpoint=GRAFANA_ENDPOINT))) == 1


class TestSignalEndpoint:
    @pytest.mark.parametrize(
        ("base_url", "signal", "expected"),
        [
            pytest.param(GRAFANA_ENDPOINT, "traces", f"{GRAFANA_ENDPOINT}/v1/traces", id="traces"),
            pytest.param(GRAFANA_ENDPOINT, "logs", f"{GRAFANA_ENDPOINT}/v1/logs", id="logs"),
            pytest.param(f"{GRAFANA_ENDPOINT}/", "logs", f"{GRAFANA_ENDPOINT}/v1/logs", id="ignora-barra-final"),
        ],
    )
    def test_anexa_o_caminho_do_sinal(self, base_url, signal, expected):
        assert signal_endpoint(base_url, signal) == expected


class TestOtlpHeaders:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("Authorization=Basic abc", {"Authorization": "Basic abc"}, id="um-header"),
            pytest.param("a=1,b=2", {"a": "1", "b": "2"}, id="dois-headers"),
            pytest.param(" a = 1 ", {"a": "1"}, id="ignora-espacos"),
            pytest.param("", {}, id="vazio"),
            pytest.param("sem-igual", {}, id="descarta-par-malformado"),
        ],
    )
    def test_converte_a_string_do_env_em_dict(self, raw, expected):
        assert ObservabilitySettings(grafana_otlp_headers=raw).otlp_headers == expected
