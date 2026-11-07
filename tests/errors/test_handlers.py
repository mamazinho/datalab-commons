import logging
from enum import StrEnum
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from pydantic import AfterValidator, BaseModel, Field

from datalab_commons.errors import FriendlyErrorHandler, FriendlyException, UnhandledErrorMiddleware

ALLOWED_ORIGIN = "https://app.datalab.test"


class NameTakenFriendlyException(FriendlyException):
    status_code = HTTPStatus.CONFLICT

    def __init__(self, name: str) -> None:
        super().__init__(
            detail={"name": name},
            message=f"The name '{name}' is taken",
            friendly_message=f'Já existe algo chamado "{name}".',
        )


class InvalidHeaderFriendlyException(FriendlyException):
    status_code = HTTPStatus.UNAUTHORIZED
    message = "Invalid header"
    friendly_message = "Cabeçalho inválido."


class Credentials(BaseModel):
    email: str
    password: int


class Plan(StrEnum):
    free = "free"
    pro = "pro"


def reject_reserved_name(name: str) -> str:
    if name == "admin":
        raise ValueError("Esse nome é reservado.")
    return name


class Signup(BaseModel):
    email: str = Field(pattern=r"^\S+@\S+$")
    name: str = Field(default="Ana", min_length=3, max_length=8)
    nickname: str = Field(default="ana", min_length=1)
    username: Annotated[str, AfterValidator(reject_reserved_name)] = "ana"
    plan: Plan = Plan.free
    company_id: UUID | None = None
    age: int = 0


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI(exception_handlers=FriendlyErrorHandler.defaults())
    application.add_middleware(UnhandledErrorMiddleware)
    application.add_middleware(CORSMiddleware, allow_origins=[ALLOWED_ORIGIN])

    @application.post("/login/")
    async def login(credentials: Credentials):
        return credentials

    @application.post("/signup/")
    async def signup(payload: Signup):
        return payload

    return application


@pytest.fixture
def raising_route(app):
    def _raise(error: Exception) -> str:
        async def endpoint():
            raise error

        app.add_api_route("/raising/", endpoint)
        return "/raising/"

    return _raise


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as http:
        yield http


class TestFriendlyException:
    async def test_answers_with_every_field_of_the_contract(self, client, raising_route):
        path = raising_route(NameTakenFriendlyException("Acme"))

        response = await client.get(path)

        assert response.status_code == 409
        assert response.json() == {
            "error": "NameTakenFriendlyException",
            "status": 409,
            "message": "The name 'Acme' is taken",
            "friendly_message": 'Já existe algo chamado "Acme".',
            "detail": {"name": "Acme"},
        }

    async def test_shows_the_error_it_was_raised_from_in_debug(self, client, raising_route, caplog):
        caplog.set_level(logging.DEBUG)
        path = raising_route(InvalidHeaderFriendlyException.caused_by(ValueError("bad api_key=sk-123")))

        response = await client.get(path)

        assert response.json()["detail"] == {"cause": {"exception": "ValueError", "reason": "bad api_key=sk-123"}}

    async def test_adds_the_cause_next_to_the_detail_it_already_has(self, client, raising_route, caplog):
        caplog.set_level(logging.DEBUG)
        error = NameTakenFriendlyException("Acme")
        error.__cause__ = LookupError("unique constraint")
        path = raising_route(error)

        response = await client.get(path)

        assert response.json()["detail"] == {
            "name": "Acme",
            "cause": {"exception": "LookupError", "reason": "unique constraint"},
        }

    async def test_keeps_the_cause_out_of_the_response_outside_debug(self, client, raising_route, caplog):
        caplog.set_level(logging.INFO)
        error = NameTakenFriendlyException("Acme")
        error.__cause__ = LookupError("unique constraint")
        path = raising_route(error)

        response = await client.get(path)

        assert response.json()["detail"] == {"name": "Acme"}

    async def test_logs_the_error_it_was_raised_from(self, client, raising_route, caplog):
        cause = ValueError("badly formed UUID string")
        path = raising_route(InvalidHeaderFriendlyException.caused_by(cause))

        with caplog.at_level(logging.WARNING):
            await client.get(path)

        [record] = [record for record in caplog.records if record.message == "Request failed because of another error"]
        assert record.exc_info is not None
        assert record.exc_info[1] is cause


class TestRoutingErrors:
    async def test_answers_an_unknown_route_in_the_contract(self, client):
        response = await client.get("/nao-existe/")

        assert response.status_code == 404
        assert response.json()["error"] == "HTTPErrorFriendlyException"
        assert response.json()["friendly_message"] == "Não encontramos o que você procurou."


class TestValidationErrors:
    async def test_keeps_the_fastapi_errors_in_the_detail(self, client):
        response = await client.post("/login/", json={"email": "ana@datalab.test"})

        assert response.status_code == 422
        assert response.json()["error"] == "RequestValidationFriendlyException"
        assert response.json()["detail"][0]["loc"] == ["body", "password"]

    @pytest.mark.parametrize(
        ("payload", "friendly_message"),
        [
            pytest.param({"nickname": ""}, "Preencha todos os campos obrigatórios.", id="blank-required-text"),
            pytest.param({"name": "An"}, "Um dos campos precisa ter ao menos 3 caracteres.", id="too-short"),
            pytest.param({"name": "Anastasia"}, "Um dos campos pode ter no máximo 8 caracteres.", id="too-long"),
            pytest.param({"email": "ana"}, "Um dos campos está em formato inválido.", id="pattern-mismatch"),
            pytest.param({"company_id": "abc"}, "Um dos identificadores enviados é inválido.", id="invalid-uuid"),
            pytest.param({"plan": "gold"}, "Uma das opções escolhidas é inválida.", id="unknown-option"),
            pytest.param({"username": "admin"}, "Esse nome é reservado.", id="custom-validator"),
            pytest.param({"age": "abc"}, "Os dados enviados são inválidos.", id="type-without-message"),
        ],
    )
    async def test_explains_the_first_problem_to_the_user(self, client, payload, friendly_message):
        response = await client.post("/signup/", json={"email": "ana@datalab.test", **payload})

        assert response.json()["friendly_message"] == friendly_message

    async def test_asks_for_the_fields_left_out(self, client):
        response = await client.post("/signup/", json={})

        assert response.json()["friendly_message"] == "Preencha todos os campos obrigatórios."

    async def test_explains_a_body_it_could_not_read(self, client):
        response = await client.post("/signup/", content="{nao-e-json", headers={"Content-Type": "application/json"})

        assert response.json()["friendly_message"] == "Não foi possível ler os dados enviados."

    async def test_never_sends_back_the_value_of_a_sensitive_field(self, client):
        response = await client.post("/login/", json={"email": "ana@datalab.test", "password": "s3nha"})

        assert response.json()["detail"][0]["input"] == "*****"

    async def test_censors_the_sensitive_fields_of_the_body_it_sends_back(self, client):
        response = await client.post("/login/", json={"password": "s3nha"})

        assert response.json()["detail"][0]["input"] == {"password": "*****"}


class TestUnhandledErrors:
    async def test_answers_in_the_contract_instead_of_plain_text(self, client, raising_route, caplog):
        caplog.set_level(logging.INFO)
        path = raising_route(RuntimeError("User disappeared right after being written"))

        response = await client.get(path)

        assert response.status_code == 500
        assert response.json()["error"] == "InternalServerErrorFriendlyException"
        assert response.json()["detail"] is None

    async def test_keeps_the_cors_headers_so_the_browser_can_read_the_error(self, client, raising_route):
        path = raising_route(RuntimeError("boom"))

        response = await client.get(path, headers={"Origin": ALLOWED_ORIGIN})

        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
