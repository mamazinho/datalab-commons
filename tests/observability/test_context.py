import uuid

import pytest

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import get_baggage


class TestLogContext:
    def test_binds_the_fields_inside_the_block(self):
        with log_context(company_id="company-1"):
            assert get_baggage() == {"company_id": "company-1"}

    def test_releases_the_fields_on_exit(self):
        with log_context(company_id="company-1"):
            pass

        assert get_baggage() == {}

    def test_stacks_onto_the_outer_context(self):
        with log_context(company_id="company-1"), log_context(chat_id="chat-9"):
            assert get_baggage() == {"company_id": "company-1", "chat_id": "chat-9"}

    def test_converts_the_value_to_text(self):
        """The project ids are UUIDs and the OpenTelemetry Baggage only accepts strings — without
        the conversion every `log_context` would emit a warning."""
        company_id = uuid.uuid4()

        with log_context(company_id=company_id):
            assert get_baggage() == {"company_id": str(company_id)}

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({"company_id": None}, id="a-null-field"),
            pytest.param({}, id="no-fields"),
        ],
    )
    def test_ignores_a_field_without_a_value(self, fields):
        with log_context(**fields):
            assert get_baggage() == {}

    def test_releases_the_fields_even_when_the_block_raises(self):
        with pytest.raises(RuntimeError), log_context(company_id="company-1"):
            raise RuntimeError("boom")

        assert get_baggage() == {}
