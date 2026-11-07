import re
from collections.abc import Mapping
from typing import Any

MASK = "*****"

SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token(?!s)|auth(?!ors?\b)|credential|private[._ -]?key|api[._ -]?key"
    r"|session|cookie|csrf|xsrf|jwt",
    re.IGNORECASE,
)
SENSITIVE_EXACT_KEYS = frozenset({"code"})

# O lookbehind mantém a busca linear em texto longo sem separador
KEY_VALUE = re.compile(
    r"""(?<![\w-])([\w-]+)(["']?\s*[:=]\s*)("[^"]*"|'[^']*'|(?:bearer\s+)?[^\s"',;&?}]+)""", re.IGNORECASE
)

TEXT_PATTERNS = (
    (re.compile(r"\b(bearer\s+)[\w.~+/=-]+", re.IGNORECASE), rf"\1{MASK}"),
    (re.compile(r"\beyJ[\w-]*\.[\w-]+\.[\w-]+"), MASK),
    (re.compile(r"(?<!\w)(\w+://)[^/\s:@]+:[^/\s@]+@"), rf"\1{MASK}@"),
    (re.compile(r"\[(SQL|parameters): [\s\S]*?\](?=\n|$)"), rf"[\1: {MASK}]"),
    (re.compile(r"(DETAIL:\s*).*"), rf"\1{MASK}"),
)


class Censor:
    @staticmethod
    def is_sensitive_key(key: Any) -> bool:
        name = str(key)
        return name.lower() in SENSITIVE_EXACT_KEYS or bool(SENSITIVE_KEY.search(name))

    @classmethod
    def censor(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: MASK if cls.is_sensitive_key(key) else cls.censor(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [cls.censor(item) for item in value]
        if isinstance(value, str):
            return cls.censor_text(value)
        return value

    @classmethod
    def censor_text(cls, text: str) -> str:
        text = KEY_VALUE.sub(cls._mask_sensitive_value, text)
        for pattern, replacement in TEXT_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    @classmethod
    def _mask_sensitive_value(cls, match: re.Match[str]) -> str:
        key, separator, value = match.groups()
        if not cls.is_sensitive_key(key):
            return match[0]
        quote = value[0] if value[0] in "\"'" else ""
        return f"{key}{separator}{quote}{MASK}{quote}"
