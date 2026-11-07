from http import HTTPStatus
from typing import Any

import httpx
from pydantic import BaseModel

from datalab_commons.censor import Censor
from datalab_commons.converter import to_snake_case
from datalab_commons.errors import ErrorResponse, FriendlyException


class UpstreamError(FriendlyException):
    status_code = HTTPStatus.BAD_GATEWAY
    friendly_message = "Um serviço de que dependemos falhou. Tente novamente em instantes."

    def __init__(self, service: str, status_code: int, body: str) -> None:
        self.upstream_status = status_code
        upstream = ErrorResponse.parse(body)
        super().__init__(
            detail={
                "service": service,
                "upstream_status": status_code,
                "upstream": Censor.censor(upstream.model_dump()) if upstream else Censor.censor_text(body),
            },
            message=f"{service} returned {status_code}",
            friendly_message=upstream.friendly_message if upstream else None,
        )


class UpstreamUnreachable(FriendlyException):
    status_code = HTTPStatus.BAD_GATEWAY
    friendly_message = "Um serviço de que dependemos não respondeu. Tente novamente em instantes."

    def __init__(self, service: str) -> None:
        super().__init__(detail={"service": service}, message=f"{service} could not be reached")


class BaseAPIClient:
    """Cliente HTTP server-to-server entre os serviços da Datalab.

    Toda falha vira 502 nomeando o serviço remoto: repassar o status do outro serviço faria um 401
    dele virar um 401 deste chamador, e o cliente deslogaria o usuário à toa.
    """

    name: str | None = None

    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        explicit = cls.__dict__.get("name")
        cls.name = explicit or to_snake_case(cls.__name__)

    async def request[ModelT: BaseModel](self, method: str, path: str, *, model: type[ModelT], **kwargs: Any) -> ModelT:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as http:
            try:
                response = await http.request(method, path.lstrip("/"), **kwargs)
            except httpx.HTTPError as exception:
                raise UpstreamUnreachable(str(self.name)) from exception

        if response.is_error:
            raise UpstreamError(str(self.name), response.status_code, response.text)

        return model.model_validate(response.json())

    async def get[ModelT: BaseModel](self, path: str, *, model: type[ModelT], **kwargs: Any) -> ModelT:
        return await self.request("GET", path, model=model, **kwargs)

    async def post[ModelT: BaseModel](self, path: str, *, model: type[ModelT], **kwargs: Any) -> ModelT:
        return await self.request("POST", path, model=model, **kwargs)

    async def put[ModelT: BaseModel](self, path: str, *, model: type[ModelT], **kwargs: Any) -> ModelT:
        return await self.request("PUT", path, model=model, **kwargs)

    async def patch[ModelT: BaseModel](self, path: str, *, model: type[ModelT], **kwargs: Any) -> ModelT:
        return await self.request("PATCH", path, model=model, **kwargs)

    async def delete[ModelT: BaseModel](self, path: str, *, model: type[ModelT], **kwargs: Any) -> ModelT:
        return await self.request("DELETE", path, model=model, **kwargs)
