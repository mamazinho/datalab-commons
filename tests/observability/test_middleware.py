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
    handler.addFilter(BaggageFilter())  # this is what `setup_logging` does on every handler
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
    logger = get_logger("test.route")
    prefixed = APIRouter(prefix="/things")

    @prefixed.get("/{item_id}/")
    async def prefixed_item(item_id: int):
        return {"item_id": item_id}

    application.include_router(prefixed, prefix="/v1")

    @application.get("/items/{item_id}")
    async def read_item(item_id: int):
        with log_context(company_id="company-1"):
            logger.info("Fetching item", item_id=item_id)
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
        raise RuntimeError("boom")

    application.add_middleware(RequestLoggingMiddleware)
    return application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as http:
        yield http


def completion_log(recorded_logs) -> logging.LogRecord:
    return next(record for record in recorded_logs.records if record.getMessage() == "Request completed")


class TestCompletionLog:
    async def test_logs_one_line_per_request(self, client, recorded_logs):
        await client.get("/items/42")

        assert len(recorded_logs.records) == 1

    async def test_logs_the_status_and_the_route_with_the_parameter_in_place_of_the_value(self, client, recorded_logs):
        """The route goes in the `/items/{item_id}` form: with the raw id every request would
        become its own series and grouping by route would stop working."""
        await client.get("/items/42")

        record = completion_log(recorded_logs)
        assert (record.http_status, record.http_route) == (200, "/items/{item_id}")

    async def test_logs_the_full_path_alongside_the_route(self, client, recorded_logs):
        await client.get("/items/42")

        record = completion_log(recorded_logs)
        assert (record.http_method, record.http_path) == ("GET", "/items/42")

    async def test_keeps_the_router_prefix_in_the_route(self, client, recorded_logs):
        """As of FastAPI 0.141 `route.path` is relative to the router: on its own it would say
        `/things/{item_id}/`, and two routers with the same inner route would become one series."""
        await client.get("/v1/things/7/")

        assert completion_log(recorded_logs).http_route == "/v1/things/{item_id}/"

    async def test_logs_the_raw_path_when_no_route_matches(self, client, recorded_logs):
        await client.get("/does/not/exist/")

        assert completion_log(recorded_logs).http_route == "/does/not/exist/"

    async def test_measures_a_streaming_response_until_the_last_chunk(self, client, recorded_logs):
        """A middleware that measured only until the response starts would report ~0ms on the chat
        routes, which are precisely the slow ones."""
        await client.get("/stream/")

        assert completion_log(recorded_logs).duration_ms >= STREAM_CHUNKS * CHUNK_DELAY_SECONDS * 1000

    async def test_logs_the_request_even_when_the_route_raises(self, client, recorded_logs):
        with pytest.raises(RuntimeError):
            await client.get("/boom/")

        assert completion_log(recorded_logs).http_status == 0


class TestExcludedPaths:
    @pytest.fixture
    def client_with_health_excluded(self, app):
        application = FastAPI()

        @application.get("/health/")
        async def health():
            return "OK"

        @application.get("/items/{item_id}")
        async def item(item_id: int):
            return {"item_id": item_id}

        application.add_middleware(RequestLoggingMiddleware, excluded_paths=["/health/"])
        return AsyncClient(transport=ASGITransport(app=application), base_url="https://test")

    async def test_does_not_log_the_excluded_route(self, client_with_health_excluded, recorded_logs):
        """The load balancer healthcheck hits every few seconds: one line per hit is thousands of
        logs a day that say nothing."""
        async with client_with_health_excluded as http:
            await http.get("/health/")

        assert recorded_logs.records == []

    async def test_keeps_logging_the_other_routes(self, client_with_health_excluded, recorded_logs):
        async with client_with_health_excluded as http:
            await http.get("/items/7")

        assert len(recorded_logs.records) == 1


class TestNonHttpScopes:
    async def test_forwards_the_lifespan_without_trying_to_log_a_request(self, recorded_logs):
        """The lifespan goes through the same middleware and has neither `method` nor `path`:
        treating it as a request would take the application down on boot, before any route
        exists."""
        received = []

        async def inner_app(scope, receive, send):
            received.append(scope["type"])

        middleware = RequestLoggingMiddleware(inner_app)
        await middleware({"type": "lifespan"}, None, None)

        assert received == ["lifespan"]
        assert recorded_logs.records == []


class TestTraceHeader:
    async def test_does_not_invent_an_id_without_instrumentation(self, client):
        """Outside a span the trace_id is invalid; returning it would hand support an id that finds
        nothing in Logfire."""
        response = await client.get("/items/42")

        assert TRACE_HEADER not in response.headers
