import logging

import pytest

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import (
    QUIET_LOGGERS,
    UVICORN_LOGGERS,
    BaggageFilter,
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
    def test_instala_o_handler_mesmo_com_o_root_ja_ocupado(self):
        """O uvicorn instala um handler no root antes da aplicação subir. Sem `force=True` o
        `basicConfig` vira no-op e nenhum log da aplicação chega ao Grafana."""
        logging.getLogger().addHandler(logging.NullHandler())

        setup_logging("INFO")

        assert logging.getLogger().level == logging.INFO

    @pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in UVICORN_LOGGERS])
    def test_religa_o_propagate_dos_loggers_do_uvicorn(self, name):
        """O uvicorn desliga o propagate deles; sem religar, "Application startup complete" e os
        erros de boot nunca saem do processo."""
        logging.getLogger(name).propagate = False

        setup_logging("INFO")

        assert logging.getLogger(name).propagate is True

    @pytest.mark.parametrize("name", [pytest.param(name, id=name) for name in QUIET_LOGGERS])
    def test_cala_as_bibliotecas_que_ja_viram_span(self, name):
        setup_logging("INFO")

        assert logging.getLogger(name).level == logging.WARNING

    def test_aplica_o_nivel_pedido(self):
        setup_logging("DEBUG")

        assert logging.getLogger().level == logging.DEBUG

    def test_poe_o_filtro_de_contexto_em_todo_handler(self):
        """Inclusive no do console: sem isto os campos do `log_context` apareceriam no Grafana mas
        sumiriam do terminal, e o mesmo log diria coisas diferentes em cada lugar."""
        setup_logging("INFO")

        handlers = logging.getLogger().handlers
        assert handlers and all(any(isinstance(f, BaggageFilter) for f in h.filters) for h in handlers)


class TestBaggageFilter:
    def test_cola_os_campos_do_contexto_no_registro(self):
        record = logging.LogRecord("teste", logging.INFO, __file__, 1, "mensagem", None, None)

        with log_context(company_id="empresa-1"):
            BaggageFilter().filter(record)

        assert record.company_id == "empresa-1"

    def test_nao_sobrescreve_campo_que_o_registro_ja_tem(self):
        record = logging.LogRecord("teste", logging.INFO, __file__, 1, "mensagem", None, None)
        record.company_id = "do-proprio-log"

        with log_context(company_id="do-contexto"):
            BaggageFilter().filter(record)

        assert record.company_id == "do-proprio-log"

    def test_fora_de_qualquer_contexto_nao_adiciona_nada(self):
        record = logging.LogRecord("teste", logging.INFO, __file__, 1, "mensagem", None, None)

        BaggageFilter().filter(record)

        assert not hasattr(record, "company_id")


class TestStructuredLogger:
    @pytest.fixture
    def recorded(self):
        handler = RecordingHandler()
        logger = logging.getLogger("teste.estruturado")
        previous_handlers, previous_level, previous_propagate = list(logger.handlers), logger.level, logger.propagate

        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        yield handler

        logger.handlers, logger.propagate = previous_handlers, previous_propagate
        logger.setLevel(previous_level)

    def test_move_os_kwargs_para_campos_do_registro(self, recorded):
        get_logger("teste.estruturado").info("Requisição concluída", http_status=200, duration_ms=12.3)

        record = recorded.records[0]
        assert (record.http_status, record.duration_ms) == (200, 12.3)

    def test_mantem_a_mensagem_sem_interpolar_os_campos(self, recorded):
        get_logger("teste.estruturado").info("Requisição concluída", http_status=200)

        assert recorded.records[0].getMessage() == "Requisição concluída"

    def test_preserva_os_argumentos_proprios_do_logging(self, recorded):
        """`exc_info` precisa continuar chegando ao logging como argumento, não virar campo —
        senão o traceback some do log de erro."""
        try:
            raise ValueError("quebrou")
        except ValueError:
            get_logger("teste.estruturado").error("Falhou", exc_info=True, company_id="empresa-1")

        record = recorded.records[0]
        assert record.exc_info is not None
        assert record.company_id == "empresa-1"
