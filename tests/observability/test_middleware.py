import asyncio
import json
import logging
import re

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace import TracerProvider

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import BaggageFilter, get_logger
from datalab_commons.observability.middleware import (
    MAX_LOGGED_BODY_CHARS,
    TRACE_RESPONSE_HEADER,
    RequestLoggingMiddleware,
)

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

    @application.post("/echo/")
    async def echo(request: Request):
        return await request.json() if request.headers.get("content-type") == "application/json" else {}

    @application.get("/token/")
    async def token():
        return {"access_token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.assinatura", "expires_in": 1800}

    @application.get("/unavailable/")
    async def unavailable():
        return Response(status_code=503)

    application.add_middleware(RequestLoggingMiddleware)
    return application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as http:
        yield http


def completion_log(recorded_logs) -> logging.LogRecord:
    return next(record for record in recorded_logs.records if record.getMessage() == "Request completed")


def start_log(recorded_logs) -> logging.LogRecord:
    return next(record for record in recorded_logs.records if record.getMessage() == "Request started")


class TestStartLog:
    async def test_logs_the_start_and_the_end_of_each_request(self, client, recorded_logs):
        await client.get("/items/42")

        assert [record.getMessage() for record in recorded_logs.records] == ["Request started", "Request completed"]

    async def test_logs_the_body_with_the_sensitive_fields_censored(self, client, recorded_logs):
        await client.post("/echo/", json={"email": "ana@datalab.test", "password": "s3nha"})

        assert json.loads(start_log(recorded_logs).http_body) == {
            "email": "ana@datalab.test",
            "password": "*****",
        }

    async def test_hands_the_body_to_the_route_untouched(self, client):
        response = await client.post("/echo/", json={"email": "ana@datalab.test", "password": "s3nha"})

        assert response.json() == {"email": "ana@datalab.test", "password": "s3nha"}

    async def test_logs_the_method_and_the_path_with_its_query_censored(self, client, recorded_logs):
        await client.get("/items/42?code=123456&page=2")

        record = start_log(recorded_logs)
        assert (record.http_method, record.http_path) == ("GET", "/items/42?code=*****&page=2")

    async def test_logs_only_the_names_of_the_headers(self, client, recorded_logs):
        await client.get("/items/42", headers={"Authorization": "Bearer eyJ.a.b"})

        record = start_log(recorded_logs)
        assert "authorization" in record.http_headers
        assert "eyJ.a.b" not in str(record.__dict__)

    async def test_logs_only_the_type_of_a_binary_body(self, client, recorded_logs):
        await client.post("/echo/", content=b"\x89PNG", headers={"Content-Type": "image/png"})

        assert start_log(recorded_logs).http_body == "<image/png>"

    async def test_cuts_a_body_bigger_than_the_limit(self, client, recorded_logs):
        await client.post("/echo/", json={"text": "a" * (MAX_LOGGED_BODY_CHARS * 2)})

        assert len(start_log(recorded_logs).http_body) == MAX_LOGGED_BODY_CHARS

    async def test_streams_an_upload_to_the_route_instead_of_holding_it(self, recorded_logs):
        chunks = [b"--limite\r\n", b"conteudo do anexo\r\n--limite--\r\n"]
        incoming = [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]
        received = []

        async def receive():
            return incoming.pop(0)

        async def send(message):
            pass

        async def upload_route(scope, receive, send):
            more_body = True
            while more_body:
                message = await receive()
                received.append(message["body"])
                more_body = message["more_body"]
            await send({"type": "http.response.start", "status": 201, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/upload/",
            "query_string": b"",
            "headers": [(b"content-type", b"multipart/form-data; boundary=limite")],
        }
        await RequestLoggingMiddleware(upload_route)(scope, receive, send)

        assert received == chunks
        assert start_log(recorded_logs).http_body == "<multipart/form-data; boundary=limite>"


class TestCompletionLog:
    async def test_logs_the_response_body_with_the_sensitive_fields_censored(self, client, recorded_logs):
        await client.get("/token/")

        assert json.loads(completion_log(recorded_logs).http_body) == {
            "access_token": "*****",
            "expires_in": 1800,
        }

    async def test_logs_the_method_the_path_and_the_status(self, client, recorded_logs):
        await client.get("/items/42?page=2")

        record = completion_log(recorded_logs)
        assert (record.http_method, record.http_path, record.http_status) == ("GET", "/items/42?page=2", 200)

    @pytest.mark.parametrize(
        ("path", "level"),
        [
            pytest.param("/items/42", logging.INFO, id="success"),
            pytest.param("/does/not/exist/", logging.WARNING, id="client-error"),
            pytest.param("/unavailable/", logging.ERROR, id="server-error"),
        ],
    )
    async def test_logs_at_the_level_of_the_status(self, client, recorded_logs, path, level):
        await client.get(path)

        assert completion_log(recorded_logs).levelno == level

    async def test_measures_a_streaming_response_until_the_last_chunk(self, client, recorded_logs):
        """A middleware that measured only until the response starts would report ~0ms on the chat
        routes, which are precisely the slow ones."""
        await client.get("/stream/")

        assert completion_log(recorded_logs).duration_ms >= STREAM_CHUNKS * CHUNK_DELAY_SECONDS * 1000

    async def test_logs_the_request_even_when_the_route_raises(self, client, recorded_logs):
        with pytest.raises(RuntimeError):
            await client.get("/boom/")

        assert (completion_log(recorded_logs).http_status, completion_log(recorded_logs).levelno) == (0, logging.ERROR)


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

        assert len(recorded_logs.records) == 2


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


class TestTraceContext:
    async def test_does_not_invent_a_trace_without_instrumentation(self, client):
        """Outside a span the trace_id is invalid; returning it would hand support an id that finds
        nothing in Logfire."""
        response = await client.get("/items/42")

        assert TRACE_RESPONSE_HEADER not in response.headers

    async def test_answers_and_logs_the_w3c_traceparent_of_the_request(self, client, recorded_logs):
        with TracerProvider().get_tracer("test").start_as_current_span("request"):
            response = await client.get("/items/42")

        traceparent = response.headers[TRACE_RESPONSE_HEADER]
        assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", traceparent)
        assert start_log(recorded_logs).traceparent == completion_log(recorded_logs).traceparent == traceparent
