from time import perf_counter

from opentelemetry import trace
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from datalab_commons.observability.context import log_context
from datalab_commons.observability.logging import get_logger

TRACE_HEADER = "X-Trace-Id"

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    """ASGI puro, e não BaseHTTPMiddleware, que atrapalha as respostas em streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        status_code = 0

        async def send_with_trace_header(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                trace_id = current_trace_id()
                if trace_id:
                    MutableHeaders(scope=message)[TRACE_HEADER] = trace_id
            await send(message)

        with log_context(http_method=scope["method"], http_path=scope["path"]):
            try:
                await self.app(scope, receive, send_with_trace_header)
            finally:
                logger.info(
                    "Requisição concluída",
                    http_route=route_template(scope),
                    http_status=status_code,
                    duration_ms=round((perf_counter() - started_at) * 1000, 2),
                )


def current_trace_id() -> str:
    context = trace.get_current_span().get_span_context()
    return trace.format_trace_id(context.trace_id) if context.is_valid else ""


def route_template(scope: Scope) -> str:
    return getattr(scope.get("route"), "path", scope["path"])
