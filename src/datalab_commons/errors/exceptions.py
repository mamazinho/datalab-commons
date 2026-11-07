import logging
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any, Self

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from datalab_commons.censor import MASK, Censor
from datalab_commons.errors.schemas import ErrorResponse


class FriendlyException(HTTPException):
    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    message: str = "Internal Server Error"
    friendly_message: str = "Algo deu errado do nosso lado. Tente novamente em instantes."

    def __init__(
        self,
        detail: Any = None,
        *,
        message: str | None = None,
        friendly_message: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=self.status_code, headers=headers)
        self.detail = detail
        self.message = message or self.message
        self.friendly_message = friendly_message or self.friendly_message

    @classmethod
    def caused_by(cls, error: BaseException) -> Self:
        exception = cls()
        exception.__cause__ = error
        return exception

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=type(self).__name__,
            status=self.status_code,
            message=self.message,
            friendly_message=self.friendly_message,
            detail=self._detail_with_cause(),
        )

    def to_json_response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content=self.to_response().model_dump(mode="json"),
            headers=self.headers,
        )

    def _detail_with_cause(self) -> Any:
        if self.__cause__ is None or not logging.getLogger().isEnabledFor(logging.DEBUG):
            return self.detail
        if self.detail is not None and not isinstance(self.detail, dict):
            return self.detail
        cause = {"exception": type(self.__cause__).__name__, "reason": str(self.__cause__)}
        return {**(self.detail or {}), "cause": cause}


class HTTPErrorFriendlyException(FriendlyException):
    FRIENDLY_MESSAGES: dict[int, str] = {
        HTTPStatus.NOT_FOUND: "Não encontramos o que você procurou.",
        HTTPStatus.METHOD_NOT_ALLOWED: "Essa operação não é permitida.",
    }

    def __init__(self, status_code: int, message: str, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        fallback = (
            "Não foi possível concluir a solicitação." if status_code < HTTPStatus.INTERNAL_SERVER_ERROR else None
        )
        super().__init__(
            message=message,
            friendly_message=self.FRIENDLY_MESSAGES.get(status_code, fallback),
            headers=headers,
        )


class RequestValidationFriendlyException(FriendlyException):
    status_code = HTTPStatus.UNPROCESSABLE_CONTENT
    message = "Request validation failed"
    friendly_message = "Os dados enviados são inválidos."
    FRIENDLY_MESSAGES = {
        "json_invalid": "Não foi possível ler os dados enviados.",
        "missing": "Preencha todos os campos obrigatórios.",
        "string_too_short": "Um dos campos precisa ter ao menos {min_length} caracteres.",
        "string_too_long": "Um dos campos pode ter no máximo {max_length} caracteres.",
        "string_pattern_mismatch": "Um dos campos está em formato inválido.",
        "uuid_parsing": "Um dos identificadores enviados é inválido.",
        "enum": "Uma das opções escolhidas é inválida.",
        "value_error": "{error}",
    }

    def __init__(self, errors: Sequence[Any]) -> None:
        super().__init__(
            detail=[self._censor(error) for error in jsonable_encoder(errors)],
            friendly_message=self._describe(errors[0]) if errors else None,
        )

    @staticmethod
    def _censor(error: dict[str, Any]) -> dict[str, Any]:
        if any(Censor.is_sensitive_key(part) for part in error.get("loc", ())):
            return {**error, "input": MASK}
        return Censor.censor(error)

    @classmethod
    def _describe(cls, error: dict[str, Any]) -> str | None:
        context = error.get("ctx", {})
        # A required text left blank fails min_length=1, and the user sees it as an empty field
        if error["type"] == "string_too_short" and context.get("min_length") == 1:
            return cls.FRIENDLY_MESSAGES["missing"]
        template = cls.FRIENDLY_MESSAGES.get(error["type"])
        return template.format(**context) if template else None


class InternalServerErrorFriendlyException(FriendlyException):
    pass
