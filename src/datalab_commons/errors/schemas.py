from typing import Any, Self

from pydantic import BaseModel, ValidationError


class ErrorResponse(BaseModel):
    error: str
    status: int
    message: str
    friendly_message: str
    detail: Any = None

    @classmethod
    def parse(cls, body: str) -> Self | None:
        try:
            return cls.model_validate_json(body)
        except ValidationError:
            return None
