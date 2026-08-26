import pytest

from datalab_commons.settings import APISettings


class TestFastapiKwargs:
    def test_exposes_the_documentation_by_default(self):
        assert APISettings().fastapi_kwargs["docs_url"] == "/docs"

    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("docs_url", id="swagger"),
            pytest.param("redoc_url", id="redoc"),
            pytest.param("openapi_url", id="openapi"),
        ],
    )
    def test_disable_docs_clears_every_documentation_path(self, key):
        """A single one leaking is enough to make the API spec public — `openapi_url` alone already
        hands out every route and schema."""
        assert APISettings(disable_docs=True).fastapi_kwargs[key] is None


class TestEnvironmentOverrides:
    @pytest.mark.parametrize(
        ("variable", "field", "expected"),
        [
            pytest.param("PORT", "port", 9000, id="port"),
            pytest.param("RELOAD", "reload", True, id="reload"),
            pytest.param("PROXY_HEADERS", "proxy_headers", False, id="proxy-headers"),
        ],
    )
    def test_reads_from_the_environment(self, monkeypatch: pytest.MonkeyPatch, variable, field, expected):
        monkeypatch.setenv(variable, str(expected))

        assert getattr(APISettings(), field) == expected

    def test_cors_requires_a_json_list_and_not_comma_separated_values(self, monkeypatch: pytest.MonkeyPatch):
        """A raw `a,b` does not become a list and takes the boot down — it has happened before, and
        the pydantic-settings error does not say which variable is wrong."""
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["https://app.test"]')

        assert APISettings().cors_allow_origins == ["https://app.test"]
