import pytest

from datalab_commons.converter import to_snake_case


class TestToSnakeCase:
    @pytest.mark.parametrize(
        ("camel_string", "expected"),
        [
            pytest.param("DatalabAPIClient", "datalab_a_p_i_client", id="consecutive-capitals-split-one-by-one"),
            pytest.param("MetaClient", "meta_client", id="two-words"),
            pytest.param("Client", "client", id="single-word-loses-leading-underscore"),
            pytest.param("already_snake", "already_snake", id="already-snake-case-is-untouched"),
            pytest.param("", "", id="empty-string"),
        ],
    )
    def test_converts_camel_case_boundaries_to_underscores(self, camel_string, expected):
        assert to_snake_case(camel_string) == expected

    @pytest.mark.parametrize(
        ("camel_string", "expected"),
        [
            pytest.param("ClientV2", "client_v_2", id="digit-becomes-its-own-word"),
            pytest.param("Oauth2Client", "oauth_2_client", id="digit-in-the-middle"),
        ],
    )
    def test_treats_digits_as_capitals_when_asked(self, camel_string, expected):
        assert to_snake_case(camel_string, treat_digits_as_capitals=True) == expected

    def test_keeps_digits_attached_to_the_word_by_default(self):
        assert to_snake_case("ClientV2") == "client_v2"
