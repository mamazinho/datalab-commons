from importlib import metadata

import pytest

from datalab_commons import version

PACKAGE_NAME = "datalab-commons"


class TestGetPackageVersion:
    def test_returns_the_installed_package_version(self):
        assert version.get_package_version(PACKAGE_NAME) == metadata.version(PACKAGE_NAME)

    def test_falls_back_when_the_package_is_not_installed(self):
        assert version.get_package_version("package-that-does-not-exist") == "unknown"

    def test_accepts_a_custom_fallback(self):
        assert version.get_package_version("package-that-does-not-exist", fallback="dev") == "dev"

    def test_does_not_swallow_other_metadata_errors(self, monkeypatch: pytest.MonkeyPatch):
        """Only `PackageNotFoundError` turns into the fallback. Swallowing the rest would hide a
        corrupted install behind an "unknown" service version."""

        def raise_unexpected(_name: str) -> str:
            raise RuntimeError("broken metadata")

        monkeypatch.setattr(version.metadata, "version", raise_unexpected)

        with pytest.raises(RuntimeError):
            version.get_package_version(PACKAGE_NAME)
