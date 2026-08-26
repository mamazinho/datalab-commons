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

SERVICE_NAME = "test-service"


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
    logger = get_logger("test.route")

    @application.get("/items/{item_id}")
    async def read_item(item_id: int):
        with log_context(company_id="company-1"):
            logger.info("Fetching item", item_id=item_id)
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
    """The logs have to come out as OpenTelemetry LogRecords, not as spans. If this breaks, they
    turn into zero-duration spans and the logs screen goes away."""

    async def test_the_application_log_reaches_the_otel_pipeline(self, client, observability):
        await client.get("/items/42")

        assert records_named(observability, "Fetching item")

    async def test_the_log_body_is_only_the_message(self, client, observability):
        """Formatted it would read "INFO:test.route:Fetching item"; the level and the logger are
        already fields of their own, and repeating them in the body gets in the way of searching by
        message."""
        await client.get("/items/42")

        bodies = [record.body for record in observability.records]
        assert "Fetching item" in bodies

    async def test_the_log_carries_the_trace_id_of_the_request(self, client, observability):
        await client.get("/items/42")

        assert records_named(observability, "Fetching item")[0].trace_id

    async def test_the_log_trace_id_is_the_one_returned_in_the_header(self, client, observability):
        """It is what support uses: with the header in hand, the whole trace can be found in
        Logfire."""
        response = await client.get("/items/42")

        record = records_named(observability, "Fetching item")[0]
        assert response.headers[TRACE_HEADER] == f"{record.trace_id:032x}"

    async def test_the_log_carries_both_the_context_fields_and_the_call_site_ones(self, client, observability):
        await client.get("/items/42")

        attributes = dict(records_named(observability, "Fetching item")[0].attributes)
        assert attributes["company_id"] == "company-1"
        assert attributes["item_id"] == 42

    async def test_the_call_site_field_does_not_leak_into_the_other_logs(self, client, observability):
        await client.get("/items/42")

        conclusion = dict(records_named(observability, "Request completed")[0].attributes)
        assert "item_id" not in conclusion


class TestDistributedTracing:
    def test_accepts_an_incoming_traceparent(self, observability):
        """It is what joins the browser, this API and the core-api into a single trace. Turned off,
        each process opens its own trace and the whole flow stops being visible at once."""
        assert logfire.DEFAULT_LOGFIRE_INSTANCE.config.distributed_tracing is True


class TestInstrumentFastapiApp:
    def test_installs_the_logging_middleware(self, app):
        assert any(middleware.cls is RequestLoggingMiddleware for middleware in app.user_middleware)

    async def test_the_excluded_route_gets_no_trace(self, client):
        """The load balancer healthcheck hits every few seconds: instrumenting it would fill the
        trace quota with traces that say nothing."""
        response = await client.get("/health/")

        assert TRACE_HEADER not in response.headers

    async def test_the_regular_route_gets_a_trace(self, client):
        response = await client.get("/items/42")

        assert response.headers[TRACE_HEADER]
