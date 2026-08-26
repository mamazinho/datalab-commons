import logging

import pytest

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import (
    CONSOLE_FORMAT,
    QUIET_LOGGERS,
    SILENT_LOGGERS,
    UVICORN_LOGGERS,
    BaggageFilter,
    ConsoleFormatter,
    get_logger,
    setup_logging,
)


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    yield
    root.handlers = previous_handlers
    root.setLevel(previous_level)


class RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestSetupLogging:
    def test_installs_the_handler_even_when_the_root_is_already_taken(self):
        """Uvicorn installs a handler on the root before the application boots. Without
        `force=True` the `basicConfig` is a no-op and no application log leaves the process."""
        logging.getLogger().addHandler(logging.NullHandler())

        setup_logging("INFO")

        assert logging.getLogger().level == logging.INFO

    @pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in UVICORN_LOGGERS])
    def test_turns_propagate_back_on_for_the_uvicorn_loggers(self, name):
        """Uvicorn turns their propagate off; without turning it back on, "Application startup
        complete" and the boot errors never leave the process."""
        logging.getLogger(name).propagate = False

        setup_logging("INFO")

        assert logging.getLogger(name).propagate is True

    @pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in QUIET_LOGGERS])
    def test_quiets_the_libraries_that_already_become_spans_or_export_telemetry(self, name):
        """`urllib3` is the transport of the OTLP exporter: on DEBUG it logs a POST for every batch
        of logs sent, that is, it logs about exporting logs."""
        setup_logging("INFO")

        assert logging.getLogger(name).level == logging.WARNING

    @pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in SILENT_LOGGERS])
    def test_silences_the_uvicorn_access_log(self, name):
        """The middleware's completion log says the same and more. Turning its propagate back on,
        as was done for the other uvicorn loggers, even undid `--no-access-log`."""
        logging.getLogger(name).propagate = True

        setup_logging("INFO")

        assert logging.getLogger(name).propagate is False

    def test_applies_the_requested_level(self):
        setup_logging("DEBUG")

        assert logging.getLogger().level == logging.DEBUG

    def test_puts_the_context_filter_on_every_handler(self):
        """Including the console one: without this the `log_context` fields would show up in
        Logfire but vanish from the terminal, and the same log would say different things in each
        place."""
        setup_logging("INFO")

        handlers = logging.getLogger().handlers
        assert handlers and all(any(isinstance(f, BaggageFilter) for f in h.filters) for h in handlers)


class TestConsoleFormatter:
    def formatted(self, **fields) -> str:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "Request completed", None, None)
        record.__dict__.update(fields)
        return ConsoleFormatter(CONSOLE_FORMAT).format(record)

    def test_shows_the_structured_fields_on_the_terminal(self):
        """Without this the same log says less on the terminal than in Logfire, and debugging
        locally becomes guesswork about what was exported."""
        assert "http_status=200" in self.formatted(http_status=200)

    def test_keeps_the_line_clean_when_there_are_no_fields(self):
        assert self.formatted().endswith("Request completed")

    def test_sorts_the_fields_so_the_line_does_not_dance_between_logs(self):
        line = self.formatted(http_status=200, company_id="company-1")

        assert line.index("company_id=") < line.index("http_status=")


class TestBaggageFilter:
    def test_attaches_the_context_fields_to_the_record(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)

        with log_context(company_id="company-1"):
            BaggageFilter().filter(record)

        assert record.company_id == "company-1"

    def test_does_not_overwrite_a_field_the_record_already_has(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)
        record.company_id = "from-the-log-itself"

        with log_context(company_id="from-the-context"):
            BaggageFilter().filter(record)

        assert record.company_id == "from-the-log-itself"

    def test_adds_nothing_outside_of_any_context(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)

        BaggageFilter().filter(record)

        assert not hasattr(record, "company_id")


class TestStructuredLogger:
    @pytest.fixture
    def recorded(self):
        handler = RecordingHandler()
        logger = logging.getLogger("test.structured")
        previous_handlers, previous_level, previous_propagate = list(logger.handlers), logger.level, logger.propagate

        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        yield handler

        logger.handlers, logger.propagate = previous_handlers, previous_propagate
        logger.setLevel(previous_level)

    def test_moves_the_kwargs_into_record_fields(self, recorded):
        get_logger("test.structured").info("Request completed", http_status=200, duration_ms=12.3)

        record = recorded.records[0]
        assert (record.http_status, record.duration_ms) == (200, 12.3)

    def test_keeps_the_message_without_interpolating_the_fields(self, recorded):
        get_logger("test.structured").info("Request completed", http_status=200)

        assert recorded.records[0].getMessage() == "Request completed"

    def test_preserves_the_logging_module_own_arguments(self, recorded):
        """`exc_info` has to keep reaching logging as an argument instead of becoming a field —
        otherwise the traceback disappears from the error log."""
        try:
            raise ValueError("boom")
        except ValueError:
            get_logger("test.structured").error("Failed", exc_info=True, company_id="company-1")

        record = recorded.records[0]
        assert record.exc_info is not None
        assert record.company_id == "company-1"
