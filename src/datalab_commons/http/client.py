from http import HTTPStatus
from typing import Any

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from datalab_commons.converter import to_snake_case


class BaseAPIClient:
    """Cliente HTTP server-to-server entre os serviços da Datalab.

    Toda falha vira 502 nomeando o serviço remoto: deixar o erro do httpx subir produziria um 500
    opaco, que não diz qual das duas APIs quebrou.
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
                raise HTTPException(HTTPStatus.BAD_GATEWAY, f"{self.name} could not be reached: {exception}")

        if response.is_error:
            raise HTTPException(HTTPStatus.BAD_GATEWAY, f"{self.name} returned {response.status_code}: {response.text}")

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
