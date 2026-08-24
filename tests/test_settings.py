import pytest

from datalab_commons.settings import APISettings


class TestFastapiKwargs:
    def test_expoe_a_documentacao_por_padrao(self):
        assert APISettings().fastapi_kwargs["docs_url"] == "/docs"

    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("docs_url", id="swagger"),
            pytest.param("redoc_url", id="redoc"),
            pytest.param("openapi_url", id="openapi"),
        ],
    )
    def test_disable_docs_apaga_todos_os_caminhos_de_documentacao(self, key):
        """Basta um deles vazando para o spec da API ficar público — o `openapi_url` sozinho já
        entrega todas as rotas e schemas."""
        assert APISettings(disable_docs=True).fastapi_kwargs[key] is None


class TestEnvironmentOverrides:
    @pytest.mark.parametrize(
        ("variable", "field", "expected"),
        [
            pytest.param("PORT", "port", 9000, id="porta"),
            pytest.param("RELOAD", "reload", True, id="reload"),
            pytest.param("PROXY_HEADERS", "proxy_headers", False, id="proxy-headers"),
        ],
    )
    def test_le_do_ambiente(self, monkeypatch: pytest.MonkeyPatch, variable, field, expected):
        monkeypatch.setenv(variable, str(expected))

        assert getattr(APISettings(), field) == expected

    def test_cors_exige_lista_json_e_nao_valores_separados_por_virgula(self, monkeypatch: pytest.MonkeyPatch):
        """Um `a,b` cru não vira lista e derruba o boot — já aconteceu, e o erro do
        pydantic-settings não diz qual variável está errada."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["https://app.test"]')

        assert APISettings().cors_allow_origins == ["https://app.test"]
