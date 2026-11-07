import time

import pytest

from datalab_commons.censor import MASK, Censor


class TestCensorText:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            pytest.param("rejected api_key=sk-123 here", "rejected api_key=***** here", id="assigned-secret"),
            pytest.param(
                '{"password": "s3nha", "email": "a@b.c"}', '{"password": "*****", "email": "a@b.c"}', id="json"
            ),
            pytest.param('{"password": "a long one"}', '{"password": "*****"}', id="quoted-value-with-spaces"),
            pytest.param("Authorization: Bearer abc.def", "Authorization: *****", id="authorization-header"),
            pytest.param("sent Bearer abc.def-123", "sent Bearer *****", id="bearer-alone"),
            pytest.param("got eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig", "got *****", id="jwt"),
            pytest.param("postgresql://app:s3nha@db:5432/x", "postgresql://*****@db:5432/x", id="url-credentials"),
            pytest.param("callback?code=123456&state=abc", "callback?code=*****&state=abc", id="confirmation-code"),
            pytest.param(
                "https://graph.facebook.com/oauth?client_secret=s3cr3t&grant_type=x",
                "https://graph.facebook.com/oauth?client_secret=*****&grant_type=x",
                id="first-query-param-of-a-url",
            ),
            pytest.param(
                "http://core-api:8001/v1/assets/?token=abc",
                "http://core-api:8001/v1/assets/?token=*****",
                id="query-after-a-port",
            ),
            pytest.param(
                "duplicate key\n[SQL: INSERT INTO users (email) VALUES ($1)]\n[parameters: ('a@b.c',)]",
                "duplicate key\n[SQL: *****]\n[parameters: *****]",
                id="sqlalchemy-query",
            ),
            pytest.param(
                "violates unique constraint\nDETAIL:  Key (email)=(a@b.c) already exists.",
                "violates unique constraint\nDETAIL:  *****",
                id="postgres-detail",
            ),
        ],
    )
    def test_masks_the_sensitive_part_and_keeps_the_rest(self, text, expected):
        assert Censor.censor_text(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("Token has expired", id="mentions-a-token"),
            pytest.param("status code 401 returned", id="mentions-a-code"),
            pytest.param("input_tokens=120 max_tokens=1000", id="token-counts"),
            pytest.param("badly formed hexadecimal UUID string", id="plain-error"),
        ],
    )
    def test_leaves_a_text_without_secrets_untouched(self, text):
        assert Censor.censor_text(text) == text

    def test_stays_fast_on_a_long_text_without_separators(self):
        started = time.perf_counter()

        Censor.censor_text("a" * 200_000)

        assert time.perf_counter() - started < 1


class TestCensor:
    def test_masks_the_values_of_sensitive_keys_at_any_depth(self):
        payload = {
            "email": "a@b.c",
            "password": "s3nha",
            "code": "123456",
            "headers": {"Authorization": "Bearer x", "X-Api-Key": "k", "User-Agent": "ff"},
            "providers": [{"access_token": "a", "provider": "google"}],
        }

        assert Censor.censor(payload) == {
            "email": "a@b.c",
            "password": MASK,
            "code": MASK,
            "headers": {"Authorization": MASK, "X-Api-Key": MASK, "User-Agent": "ff"},
            "providers": [{"access_token": MASK, "provider": "google"}],
        }

    def test_keeps_keys_that_only_resemble_sensitive_ones(self):
        payload = {"input_tokens": 5, "max_tokens": 9, "status_code": 401, "error_code": "E1", "author": "Ana"}

        assert Censor.censor(payload) == payload

    def test_censors_the_text_of_a_value_under_a_harmless_key(self):
        assert Censor.censor({"reason": "rejected api_key=sk-1"}) == {"reason": "rejected api_key=*****"}
