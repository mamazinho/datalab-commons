import asyncio
import logging

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import BaggageFilter, get_logger
from datalab_commons.observability.middleware import TRACE_HEADER, RequestLoggingMiddleware

STREAM_CHUNKS = 3
CHUNK_DELAY_SECONDS = 0.02


class RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def recorded_logs():
    handler = RecordingHandler()
    handler.addFilter(BaggageFilter())  # é o que o `setup_logging` faz em todo handler
    logger = logging.getLogger("datalab_commons.observability.middleware")
    previous_handlers, previous_level, previous_propagate = list(logger.handlers), logger.level, logger.propagate

    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    yield handler

    logger.handlers, logger.propagate = previous_handlers, previous_propagate
    logger.setLevel(previous_level)


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    logger = get_logger("teste.rota")
    prefixed = APIRouter(prefix="/coisas")

    @prefixed.get("/{item_id}/")
    async def prefixed_item(item_id: int):
        return {"item_id": item_id}

    application.include_router(prefixed, prefix="/v1")

    @application.get("/items/{item_id}")
    async def read_item(item_id: int):
        with log_context(company_id="empresa-1"):
            logger.info("Buscando item", item_id=item_id)
        return {"item_id": item_id}

    @application.get("/stream/")
    async def stream():
        async def body():
            for index in range(STREAM_CHUNKS):
                await asyncio.sleep(CHUNK_DELAY_SECONDS)
                yield f"{index}\n".encode()

        return StreamingResponse(body(), media_type="application/x-ndjson")

    @application.get("/boom/")
    async def boom():
        raise RuntimeError("quebrou")

    application.add_middleware(RequestLoggingMiddleware)
    return application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as http:
        yield http


def completion_log(recorded_logs) -> logging.LogRecord:
    return next(record for record in recorded_logs.records if record.getMessage() == "Request completed")


class TestCompletionLog:
    async def test_registra_uma_linha_por_requisicao(self, client, recorded_logs):
        await client.get("/items/42")

        assert len(recorded_logs.records) == 1

    async def test_registra_o_status_e_a_rota_com_o_parametro_no_lugar_do_valor(self, client, recorded_logs):
        """A rota vai no formato `/items/{item_id}`: com o id cru cada requisição viraria uma
        série própria no Grafana e agrupar por rota deixaria de funcionar."""
        await client.get("/items/42")

        record = completion_log(recorded_logs)
        assert (record.http_status, record.http_route) == (200, "/items/{item_id}")

    async def test_registra_o_caminho_completo_junto_da_rota(self, client, recorded_logs):
        await client.get("/items/42")

        record = completion_log(recorded_logs)
        assert (record.http_method, record.http_path) == ("GET", "/items/42")

    async def test_mantem_o_prefixo_do_router_na_rota(self, client, recorded_logs):
        """A partir do FastAPI 0.141 o `route.path` é relativo ao router: sozinho ele diria
        `/coisas/{item_id}/`, e dois routers com a mesma rota interna virariam a mesma série."""
        await client.get("/v1/coisas/7/")

        assert completion_log(recorded_logs).http_route == "/v1/coisas/{item_id}/"

    async def test_sem_rota_casada_registra_o_caminho_cru(self, client, recorded_logs):
        await client.get("/nao/existe/")

        assert completion_log(recorded_logs).http_route == "/nao/existe/"

    async def test_mede_a_resposta_em_streaming_ate_o_ultimo_pedaco(self, client, recorded_logs):
        """Um middleware que medisse só até a resposta começar marcaria ~0ms nas rotas de chat,
        que são justamente as lentas."""
        await client.get("/stream/")

        assert completion_log(recorded_logs).duration_ms >= STREAM_CHUNKS * CHUNK_DELAY_SECONDS * 1000

    async def test_registra_a_requisicao_mesmo_quando_a_rota_levanta(self, client, recorded_logs):
        with pytest.raises(RuntimeError):
            await client.get("/boom/")

        assert completion_log(recorded_logs).http_status == 0


class TestExcludedPaths:
    @pytest.fixture
    def client_com_health_excluido(self, app):
        application = FastAPI()

        @application.get("/health/")
        async def health():
            return "OK"

        @application.get("/items/{item_id}")
        async def item(item_id: int):
            return {"item_id": item_id}

        application.add_middleware(RequestLoggingMiddleware, excluded_paths=["/health/"])
        return AsyncClient(transport=ASGITransport(app=application), base_url="https://test")

    async def test_nao_loga_a_rota_excluida(self, client_com_health_excluido, recorded_logs):
        """O healthcheck do balanceador bate a cada poucos segundos: uma linha por batida são
        milhares de logs por dia que não dizem nada."""
        async with client_com_health_excluido as http:
            await http.get("/health/")

        assert recorded_logs.records == []

    async def test_segue_logando_as_demais(self, client_com_health_excluido, recorded_logs):
        async with client_com_health_excluido as http:
            await http.get("/items/7")

        assert len(recorded_logs.records) == 1


class TestNonHttpScopes:
    async def test_repassa_o_lifespan_sem_tentar_logar_uma_requisicao(self, recorded_logs):
        """O lifespan passa pelo mesmo middleware e não tem `method` nem `path`: tratá-lo como
        requisição derrubaria a aplicação no boot, antes de qualquer rota existir."""
        received = []

        async def inner_app(scope, receive, send):
            received.append(scope["type"])

        middleware = RequestLoggingMiddleware(inner_app)
        await middleware({"type": "lifespan"}, None, None)

        assert received == ["lifespan"]
        assert recorded_logs.records == []


class TestTraceHeader:
    async def test_sem_instrumentacao_nao_inventa_um_id(self, client):
        """Fora de um span o trace_id é inválido; devolvê-lo daria ao suporte um id que não acha
        nada nem no Grafana nem no Logfire."""
        response = await client.get("/items/42")

        assert TRACE_HEADER not in response.headers
