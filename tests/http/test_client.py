from http import HTTPStatus

import httpx
import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from datalab_commons.http.client import BaseAPIClient, UpstreamError, UpstreamUnreachable

BASE_URL = "https://provider.test/v1"


class Echo(BaseModel):
    value: str


class EchoAPIClient(BaseAPIClient):
    async def fetch(self, path: str, **kwargs) -> Echo:
        return await self.get(path, model=Echo, **kwargs)


@pytest.fixture
def client() -> EchoAPIClient:
    return EchoAPIClient(BASE_URL, timeout=1.0)


class TestSubclassNaming:
    def test_derives_the_name_from_the_class_name(self):
        class SimpleClient(BaseAPIClient):
            pass

        assert SimpleClient.name == "simple_client"

    def test_an_explicit_name_wins_over_the_derived_one(self):
        class WeirdlyNamedClient(BaseAPIClient):
            name = "meta"

        assert WeirdlyNamedClient.name == "meta"


class TestBaseUrlNormalization:
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            pytest.param("https://provider.test/v1", "https://provider.test/v1/", id="adds-the-trailing-slash"),
            pytest.param("https://provider.test/v1/", "https://provider.test/v1/", id="keeps-a-single-trailing-slash"),
            pytest.param(
                "https://provider.test/v1///", "https://provider.test/v1/", id="collapses-repeated-trailing-slashes"
            ),
        ],
    )
    def test_always_ends_in_exactly_one_slash(self, configured, expected):
        assert BaseAPIClient(configured, timeout=1.0).base_url == expected


class TestRequest:
    async def test_validates_the_response_into_the_requested_model(self, client, respx_mock):
        respx_mock.get(f"{BASE_URL}/things/").mock(return_value=httpx.Response(200, json={"value": "ok"}))

        assert await client.fetch("things/") == Echo(value="ok")

    async def test_joins_the_path_onto_the_base_url_without_swallowing_the_prefix(self, client, respx_mock):
        route = respx_mock.get(f"{BASE_URL}/things/").mock(return_value=httpx.Response(200, json={"value": "ok"}))

        await client.fetch("/things/")

        assert str(route.calls.last.request.url) == f"{BASE_URL}/things/"

    async def test_forwards_extra_kwargs_to_httpx(self, client, respx_mock):
        route = respx_mock.get(f"{BASE_URL}/things/").mock(return_value=httpx.Response(200, json={"value": "ok"}))

        await client.fetch("things/", headers={"X-Custom": "1"}, params={"page": 2})

        request = route.calls.last.request
        assert request.headers["X-Custom"] == "1"
        assert request.url.params["page"] == "2"

    @pytest.mark.parametrize(
        "status_code",
        [
            pytest.param(400, id="bad-request"),
            pytest.param(401, id="unauthorized"),
            pytest.param(403, id="forbidden"),
            pytest.param(500, id="server-error"),
        ],
    )
    async def test_turns_any_error_status_into_a_bad_gateway(self, client, respx_mock, status_code):
        """Any upstream failure becomes a 502, not its own status: a 401 coming from the other API
        is not a 401 from this caller, and forwarding it would log the user out for nothing."""
        respx_mock.get(f"{BASE_URL}/things/").mock(return_value=httpx.Response(status_code, json={}))

        with pytest.raises(HTTPException) as raised:
            await client.fetch("things/")

        assert raised.value.status_code == HTTPStatus.BAD_GATEWAY

    async def test_names_the_remote_service_and_its_status_in_the_error(self, client, respx_mock):
        """It is what separates "the core-api returned 500" from a generic 500 when reading the
        alert."""
        respx_mock.get(f"{BASE_URL}/things/").mock(return_value=httpx.Response(503, text="unavailable"))

        with pytest.raises(UpstreamError) as raised:
            await client.fetch("things/")

        assert raised.value.detail == f"{EchoAPIClient.name} returned 503: unavailable"

    async def test_carries_the_upstream_status_so_the_caller_can_react_to_it(self, client, respx_mock):
        """Without this field, telling "it rejected the caller" apart from "it broke" would mean
        parsing the message — and callers handle the two cases differently."""
        respx_mock.get(f"{BASE_URL}/things/").mock(return_value=httpx.Response(403, json={}))

        with pytest.raises(UpstreamError) as raised:
            await client.fetch("things/")

        assert raised.value.upstream_status == 403

    async def test_turns_a_transport_failure_into_a_distinct_exception(self, client, respx_mock):
        respx_mock.get(f"{BASE_URL}/things/").mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(UpstreamUnreachable) as raised:
            await client.fetch("things/")

        assert raised.value.status_code == HTTPStatus.BAD_GATEWAY
        assert "could not be reached" in raised.value.detail

    @pytest.mark.parametrize(
        "verb",
        [
            pytest.param("get", id="get"),
            pytest.param("post", id="post"),
            pytest.param("put", id="put"),
            pytest.param("patch", id="patch"),
            pytest.param("delete", id="delete"),
        ],
    )
    async def test_exposes_one_helper_per_common_verb(self, client, respx_mock, verb):
        route = respx_mock.request(verb.upper(), f"{BASE_URL}/things/").mock(
            return_value=httpx.Response(200, json={"value": "ok"})
        )

        result = await getattr(client, verb)("things/", model=Echo)

        assert result == Echo(value="ok")
        assert route.calls.last.request.method == verb.upper()

    async def test_supports_uncommon_verbs_through_the_generic_request(self, client, respx_mock):
        route = respx_mock.request("QUERY", f"{BASE_URL}/things/").mock(
            return_value=httpx.Response(200, json={"value": "ok"})
        )

        await client.request("QUERY", "things/", model=Echo, json={"q": 1})

        assert route.calls.last.request.method == "QUERY"
