from contextlib import AbstractContextManager

import logfire


def log_context(**fields: object) -> AbstractContextManager[None]:
    """Prende campos ao contexto atual: eles aparecem em todo log e span abertos dentro do bloco.

    Ficam dentro do processo: o `configure_observability` propaga só o traceparent.
    """
    values = {key: str(value) for key, value in fields.items() if value is not None}
    return logfire.set_baggage(**values)
