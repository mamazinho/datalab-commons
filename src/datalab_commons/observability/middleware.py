import json
import logging
from collections.abc import Sequence
from time import perf_counter

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from datalab_commons.censor import Censor
from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import get_logger

TRACEPARENT_HEADER = "traceparent"
TRACE_RESPONSE_HEADER = "traceresponse"
MAX_LOGGED_BODY_CHARS = 10_000

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp, excluded_paths: Sequence[str] = ()) -> None:
        self.app = app
        self.excluded_paths = frozenset(excluded_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.excluded_paths:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_body = b""
        if has_text_body(request.headers):
            request_body = await request.body()
            receive = replay_body(request_body, receive)

        path = request.url.path
        if request.url.query:
            path = f"{path}?{Censor.censor_text(request.url.query)}"
        traceparent = current_traceparent()
        response_start: Message = {"status": 0, "headers": []}
        response_body = bytearray()

        async def send_logging(message: Message) -> None:
            if message["type"] == "http.response.start":
                if traceparent:
                    MutableHeaders(scope=message)[TRACE_RESPONSE_HEADER] = traceparent
                response_start.update(message)
            elif len(response_body) < MAX_LOGGED_BODY_CHARS:
                response_body.extend(message.get("body", b""))
            await send(message)

        with log_context(http_method=request.method, http_path=path):
            logger.info(
                "Request started",
                http_headers=list(request.headers.keys()),
                http_body=loggable_body(request.headers, request_body),
                traceparent=traceparent,
            )
            started_at = perf_counter()
            try:
                await self.app(scope, receive, send_logging)
            finally:
                response_headers = Headers(raw=response_start["headers"])
                logger.log(
                    completion_level(response_start["status"]),
                    "Request completed",
                    http_status=response_start["status"],
                    duration_ms=round((perf_counter() - started_at) * 1000, 2),
                    http_headers=list(response_headers.keys()),
                    http_body=loggable_body(response_headers, response_body),
                    traceparent=traceparent,
                )


def completion_level(status: int) -> int:
    if status >= 500 or status == 0:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO


def has_text_body(headers: Headers) -> bool:
    content_type = headers.get("content-type", "")
    return "json" in content_type or content_type.startswith("text/")


def replay_body(body: bytes, receive: Receive) -> Receive:
    pending: list[Message] = [{"type": "http.request", "body": body}]

    async def replay() -> Message:
        return pending.pop() if pending else await receive()

    return replay


def loggable_body(headers: Headers, body: bytes | bytearray) -> str | None:
    if not has_text_body(headers):
        return f"<{headers['content-type']}>" if "content-type" in headers else None
    if not body:
        return None

    try:
        text = json.dumps(Censor.censor(json.loads(body)), ensure_ascii=False)
    except ValueError:
        text = Censor.censor_text(body.decode("utf-8", errors="replace"))
    return text[:MAX_LOGGED_BODY_CHARS]


def current_traceparent() -> str:
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    return carrier.get(TRACEPARENT_HEADER, "")
