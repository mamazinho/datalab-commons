import logging

import logfire
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk._logs import LogRecordProcessor

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import get_logger
from datalab_commons.observability.middleware import TRACE_HEADER, RequestLoggingMiddleware
from datalab_commons.observability.setup import configure_observability, instrument_fastapi_app

SERVICE_NAME = "servico-de-teste"


class CapturingLogProcessor(LogRecordProcessor):
    def __init__(self) -> None:
        self.records = []

    def on_emit(self, log_data):
        self.records.append(log_data.log_record)

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30_000):
        return True


@pytest.fixture
def observability(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONSOLE_SPANS", "false")
    monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)

    root = logging.getLogger()
    previous_handlers, previous_level = list(root.handlers), root.level

    configure_observability(SERVICE_NAME, "1.2.3")
    captured = CapturingLogProcessor()
    logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_logger_provider().add_log_record_processor(captured)

    yield captured

    logfire.shutdown()
    root.handlers, root.level = previous_handlers, previous_level


@pytest.fixture
def app(observability) -> FastAPI:
    application = FastAPI()
    logger = get_logger("teste.rota")

    @application.get("/items/{item_id}")
    async def read_item(item_id: int):
        with log_context(company_id="empresa-1"):
            logger.info("Buscando item", item_id=item_id)
        return {"item_id": item_id}

    @application.get("/health/")
    async def health():
        return "OK"

    instrument_fastapi_app(application, excluded_urls=["/health/"])
    return application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as http:
        yield http


def records_named(captured, message: str) -> list:
    return [record for record in captured.records if record.body == message]


class TestLogPipeline:
    """Os logs precisam sair como LogRecord do OpenTelemetry, e não como span. Se isto quebrar,
    eles viram spans de duração zero e some a tela de logs."""

    async def test_o_log_da_aplicacao_chega_ao_pipeline_otel(self, client, observability):
        await client.get("/items/42")

        assert records_named(observability, "Buscando item")

    async def test_o_corpo_do_log_e_so_a_mensagem(self, client, observability):
        """Formatado viria "INFO:teste.rota:Buscando item"; o nível e o logger já são campos
        próprios, e repeti-los no corpo atrapalha buscar por mensagem."""
        await client.get("/items/42")

        bodies = [record.body for record in observability.records]
        assert "Buscando item" in bodies

    async def test_o_log_carrega_o_trace_id_do_request(self, client, observability):
        await client.get("/items/42")

        assert records_named(observability, "Buscando item")[0].trace_id

    async def test_o_trace_id_do_log_e_o_mesmo_devolvido_no_header(self, client, observability):
        """É o que o suporte usa: com o header em mãos, acha-se o trace inteiro no Logfire."""
        response = await client.get("/items/42")

        record = records_named(observability, "Buscando item")[0]
        assert response.headers[TRACE_HEADER] == f"{record.trace_id:032x}"

    async def test_o_log_carrega_os_campos_do_contexto_e_os_da_linha(self, client, observability):
        await client.get("/items/42")

        attributes = dict(records_named(observability, "Buscando item")[0].attributes)
        assert attributes["company_id"] == "empresa-1"
        assert attributes["item_id"] == 42

    async def test_o_campo_da_linha_nao_vaza_para_os_outros_logs(self, client, observability):
        await client.get("/items/42")

        conclusion = dict(records_named(observability, "Request completed")[0].attributes)
        assert "item_id" not in conclusion


class TestDistributedTracing:
    def test_aceita_traceparent_de_entrada(self, observability):
        """É o que junta navegador, esta API e a core-api num trace só. Desligado, cada processo
        abre o próprio trace e o fluxo inteiro deixa de ser visível de uma vez."""
        assert logfire.DEFAULT_LOGFIRE_INSTANCE.config.distributed_tracing is True


class TestInstrumentFastapiApp:
    def test_instala_o_middleware_de_log(self, app):
        assert any(middleware.cls is RequestLoggingMiddleware for middleware in app.user_middleware)

    async def test_a_rota_excluida_nao_recebe_trace(self, client):
        """O healthcheck do balanceador bate a cada poucos segundos: instrumentá-lo encheria a
        cota de traces que não dizem nada."""
        response = await client.get("/health/")

        assert TRACE_HEADER not in response.headers

    async def test_a_rota_normal_recebe_trace(self, client):
        response = await client.get("/items/42")

        assert response.headers[TRACE_HEADER]
