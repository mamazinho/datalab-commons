import mimetypes
import urllib.parse

GENERIC_MEDIA_TYPE = "application/octet-stream"
DEFAULT_FILENAME = "arquivo"
MAX_FILENAME_LENGTH = 255

IMAGE_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
TEXT_MEDIA_TYPES = frozenset({"application/json", "application/xml", "application/yaml", "application/x-yaml"})
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
OFFICE_MEDIA_TYPES = frozenset({DOCX_MEDIA_TYPE, XLSX_MEDIA_TYPE, PPTX_MEDIA_TYPE})

_mime_types = mimetypes.MimeTypes()
_mime_types.add_type(DOCX_MEDIA_TYPE, ".docx")
_mime_types.add_type(XLSX_MEDIA_TYPE, ".xlsx")
_mime_types.add_type(PPTX_MEDIA_TYPE, ".pptx")
_mime_types.add_type("text/markdown", ".md")
_mime_types.add_type("application/xml", ".xml")


def guess_media_type(content_type: str | None, filename: str) -> str:
    media_type = (content_type or "").split(";")[0].strip().lower()
    if media_type and media_type != GENERIC_MEDIA_TYPE:
        return media_type
    guessed, _ = _mime_types.guess_type(filename)
    return guessed or GENERIC_MEDIA_TYPE


def is_text_media_type(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in TEXT_MEDIA_TYPES or media_type.endswith(("+json", "+xml"))


def is_image_media_type(media_type: str) -> bool:
    return media_type in IMAGE_MEDIA_TYPES


def is_office_media_type(media_type: str) -> bool:
    return media_type in OFFICE_MEDIA_TYPES


def normalize_filename(filename: str | None, extension: str | None = None) -> str:
    name = (filename or "").strip().replace("/", "-").replace("\\", "-") or DEFAULT_FILENAME
    suffix = f".{extension}" if extension else ""
    if suffix and name.lower().endswith(suffix):
        name = name[: -len(suffix)] or DEFAULT_FILENAME
    return f"{name[: MAX_FILENAME_LENGTH - len(suffix)]}{suffix}"


def content_disposition(filename: str) -> str:
    ascii_name = "".join(
        char for char in filename.encode("ascii", "ignore").decode("ascii") if char.isprintable() and char not in '"\\'
    )
    quoted = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name or DEFAULT_FILENAME}\"; filename*=UTF-8''{quoted}"
