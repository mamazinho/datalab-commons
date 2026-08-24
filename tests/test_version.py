from importlib import metadata

import pytest

from datalab_commons import version

PACKAGE_NAME = "datalab-commons"


class TestGetPackageVersion:
    def test_returns_the_installed_package_version(self):
        assert version.get_package_version(PACKAGE_NAME) == metadata.version(PACKAGE_NAME)

    def test_falls_back_when_the_package_is_not_installed(self):
        assert version.get_package_version("pacote-que-nao-existe") == "unknown"

    def test_accepts_a_custom_fallback(self):
        assert version.get_package_version("pacote-que-nao-existe", fallback="dev") == "dev"

    def test_does_not_swallow_other_metadata_errors(self, monkeypatch: pytest.MonkeyPatch):
        """Só `PackageNotFoundError` vira fallback. Engolir o resto esconderia instalação
        corrompida atrás de um "unknown" na versão do serviço."""

        def raise_unexpected(_name: str) -> str:
            raise RuntimeError("metadata quebrada")

        monkeypatch.setattr(version.metadata, "version", raise_unexpected)

        with pytest.raises(RuntimeError):
            version.get_package_version(PACKAGE_NAME)
