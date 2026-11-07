import abc
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from datalab_commons.errors.exceptions import (
    FriendlyException,
    HTTPErrorFriendlyException,
    InternalServerErrorFriendlyException,
    RequestValidationFriendlyException,
)
from datalab_commons.observability.logging import get_logger

logger = get_logger(__name__)

ExceptionHandlers = dict[int | type[Exception], Callable[[Request, Any], Coroutine[Any, Any, Response]]]


class FriendlyErrorHandler[ExceptionT: Exception](abc.ABC):
    @abc.abstractmethod
    def to_friendly(self, exception: ExceptionT) -> FriendlyException: ...

    async def __call__(self, request: Request, exception: ExceptionT) -> JSONResponse:
        friendly = self.to_friendly(exception)
        if friendly.__cause__ is not None:
            logger.warning(
                "Request failed because of another error",
                error=type(friendly).__name__,
                exc_info=friendly.__cause__,
            )
        return friendly.to_json_response()

    @staticmethod
    def defaults() -> ExceptionHandlers:
        return {
            StarletteHTTPException: HTTPExceptionHandler(),
            RequestValidationError: RequestValidationErrorHandler(),
        }


class HTTPExceptionHandler(FriendlyErrorHandler[StarletteHTTPException]):
    def to_friendly(self, exception: StarletteHTTPException) -> FriendlyException:
        if isinstance(exception, FriendlyException):
            return exception
        headers = dict(exception.headers) if exception.headers else None
        return HTTPErrorFriendlyException(exception.status_code, str(exception.detail), headers)


class RequestValidationErrorHandler(FriendlyErrorHandler[RequestValidationError]):
    def to_friendly(self, exception: RequestValidationError) -> FriendlyException:
        return RequestValidationFriendlyException(exception.errors())


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_start: list[Message] = []

        async def send_capturing_start(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_start.append(message)
            await send(message)

        try:
            await self.app(scope, receive, send_capturing_start)
        except Exception as error:
            if response_start:
                raise
            logger.exception("Unhandled error")
            await InternalServerErrorFriendlyException.caused_by(error).to_json_response()(scope, receive, send)
