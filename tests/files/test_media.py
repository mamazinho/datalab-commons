import pytest

from datalab_commons.files import (
    DOCX_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
    content_disposition,
    guess_media_type,
    is_image_media_type,
    is_office_media_type,
    is_text_media_type,
    normalize_filename,
)


class TestGuessMediaType:
    @pytest.mark.parametrize(
        ("content_type", "filename", "expected"),
        [
            pytest.param("text/csv", "data.bin", "text/csv", id="declared-type-wins"),
            pytest.param("text/csv; charset=utf-8", "data.csv", "text/csv", id="parameters-are-dropped"),
            pytest.param("application/octet-stream", "note.pdf", "application/pdf", id="generic-falls-back-to-name"),
            pytest.param(None, "sheet.xlsx", XLSX_MEDIA_TYPE, id="xlsx-is-known-by-extension"),
            pytest.param(None, "letter.docx", DOCX_MEDIA_TYPE, id="docx-is-known-by-extension"),
            pytest.param(None, "noextension", "application/octet-stream", id="unknown-stays-generic"),
        ],
    )
    def test_resolves_the_media_type(self, content_type, filename, expected):
        assert guess_media_type(content_type, filename) == expected


class TestMediaTypeGroups:
    @pytest.mark.parametrize(
        ("media_type", "text", "image", "office"),
        [
            pytest.param("text/csv", True, False, False, id="csv-is-text"),
            pytest.param("application/ld+json", True, False, False, id="json-suffix-is-text"),
            pytest.param("image/png", False, True, False, id="png-is-image"),
            pytest.param(XLSX_MEDIA_TYPE, False, False, True, id="xlsx-is-office"),
            pytest.param("application/pdf", False, False, False, id="pdf-is-none-of-them"),
        ],
    )
    def test_classifies(self, media_type, text, image, office):
        assert is_text_media_type(media_type) is text
        assert is_image_media_type(media_type) is image
        assert is_office_media_type(media_type) is office


class TestNormalizeFilename:
    @pytest.mark.parametrize(
        ("filename", "extension", "expected"),
        [
            pytest.param("report", "pdf", "report.pdf", id="missing-extension-is-added"),
            pytest.param("report.pdf", "pdf", "report.pdf", id="right-extension-is-kept"),
            pytest.param("report.PDF", "pdf", "report.pdf", id="uppercase-extension-is-normalised"),
            pytest.param("  ", "pdf", "arquivo.pdf", id="blank-name-gets-a-default"),
            pytest.param(None, None, "arquivo", id="upload-without-name-gets-a-default"),
            pytest.param("a/b\\c", "pdf", "a-b-c.pdf", id="path-separators-are-flattened"),
        ],
    )
    def test_normalises(self, filename, extension, expected):
        assert normalize_filename(filename, extension) == expected

    def test_keeps_the_name_within_the_column_limit(self):
        name = normalize_filename("a" * 400, "pdf")

        assert len(name) == 255
        assert name.endswith(".pdf")


class TestContentDisposition:
    def test_carries_the_real_name_and_an_ascii_fallback(self):
        header = content_disposition("relatório final.pdf")

        assert 'filename="relatrio final.pdf"' in header
        assert "filename*=UTF-8''relat%C3%B3rio%20final.pdf" in header

    def test_quotes_in_the_name_do_not_break_the_header(self):
        assert 'filename="quoted.pdf"' in content_disposition('quo"ted.pdf')
