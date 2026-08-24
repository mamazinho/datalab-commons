import uuid

import pytest

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import get_baggage


class TestLogContext:
    def test_prende_os_campos_dentro_do_bloco(self):
        with log_context(company_id="empresa-1"):
            assert get_baggage() == {"company_id": "empresa-1"}

    def test_solta_os_campos_ao_sair(self):
        with log_context(company_id="empresa-1"):
            pass

        assert get_baggage() == {}

    def test_acumula_com_o_contexto_de_fora(self):
        with log_context(company_id="empresa-1"), log_context(chat_id="chat-9"):
            assert get_baggage() == {"company_id": "empresa-1", "chat_id": "chat-9"}

    def test_converte_o_valor_para_texto(self):
        """Os ids do projeto são UUID, e o Baggage do OpenTelemetry só aceita string — sem a
        conversão cada `log_context` sairia com um warning."""
        company_id = uuid.uuid4()

        with log_context(company_id=company_id):
            assert get_baggage() == {"company_id": str(company_id)}

    @pytest.mark.parametrize(
        "fields",
        [
            pytest.param({"company_id": None}, id="um-campo-nulo"),
            pytest.param({}, id="nenhum-campo"),
        ],
    )
    def test_ignora_campo_sem_valor(self, fields):
        with log_context(**fields):
            assert get_baggage() == {}

    def test_solta_os_campos_mesmo_quando_o_bloco_levanta(self):
        with pytest.raises(RuntimeError), log_context(company_id="empresa-1"):
            raise RuntimeError("quebrou")

        assert get_baggage() == {}
