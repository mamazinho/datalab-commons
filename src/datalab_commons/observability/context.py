from contextlib import AbstractContextManager

import logfire


def log_context(**fields: object) -> AbstractContextManager[None]:
    """Prende campos ao contexto atual: eles aparecem em todo log e span abertos dentro do bloco.

    Usa Baggage do OpenTelemetry, e não contextvars soltos, porque o Baggage viaja no header da
    requisição — os mesmos campos reaparecem nos spans da core-api.
    """
    values = {key: str(value) for key, value in fields.items() if value is not None}
    return logfire.set_baggage(**values)
