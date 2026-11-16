import asyncio
import uuid

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from datalab_commons.observability.context import MAX_FIELD_LENGTH, LogFields, LogFieldsSpanProcessor


@pytest.fixture(autouse=True)
def fresh_fields():
    with LogFields.scope():
        yield


class TestLogFields:
    def test_adds_the_fields_to_the_current_context(self):
        LogFields.add(company_id="company-1")

        assert LogFields.current() == {"company_id": "company-1"}

    def test_accumulates_without_nesting(self):
        LogFields.add(company_id="company-1")
        LogFields.add(chat_id="chat-9")

        assert LogFields.current() == {"company_id": "company-1", "chat_id": "chat-9"}

    def test_a_later_value_replaces_the_earlier_one(self):
        LogFields.add(entity_ids="a")
        LogFields.add(entity_ids="a,b")

        assert LogFields.current() == {"entity_ids": "a,b"}

    def test_converts_the_value_to_text(self):
        company_id = uuid.uuid4()

        LogFields.add(company_id=company_id)

        assert LogFields.current() == {"company_id": str(company_id)}

    def test_cuts_a_value_longer_than_the_limit(self):
        LogFields.add(entity_ids="a" * (MAX_FIELD_LENGTH * 2))

        assert len(LogFields.current()["entity_ids"]) == MAX_FIELD_LENGTH

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({"company_id": None}, id="a-null-field"),
            pytest.param({}, id="no-fields"),
        ],
    )
    def test_ignores_a_field_without_a_value(self, fields):
        LogFields.add(**fields)

        assert LogFields.current() == {}

    def test_the_scope_starts_empty_and_restores_the_outer_fields(self):
        LogFields.add(company_id="company-1")

        with LogFields.scope():
            assert LogFields.current() == {}
            LogFields.add(chat_id="chat-9")

        assert LogFields.current() == {"company_id": "company-1"}

    async def test_concurrent_tasks_do_not_see_each_other_fields(self):
        async def request(company_id: str) -> dict[str, str]:
            LogFields.add(company_id=company_id)
            await asyncio.sleep(0.01)
            return dict(LogFields.current())

        assert await asyncio.gather(request("a"), request("b")) == [{"company_id": "a"}, {"company_id": "b"}]


class TestLogFieldsSpanProcessor:
    @pytest.fixture
    def tracer(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(LogFieldsSpanProcessor())
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return provider.get_tracer("test"), exporter

    def test_puts_the_fields_on_every_span_opened(self, tracer):
        tracer, exporter = tracer
        LogFields.add(company_id="company-1")

        tracer.start_span("query").end()

        assert exporter.get_finished_spans()[0].attributes == {"company_id": "company-1"}

    def test_does_not_overwrite_an_attribute_the_span_already_has(self, tracer):
        tracer, exporter = tracer
        LogFields.add(company_id="from-the-context")

        tracer.start_span("query", attributes={"company_id": "from-the-span"}).end()

        assert exporter.get_finished_spans()[0].attributes == {"company_id": "from-the-span"}
