"""Shared JSON reading: nothing may become a float on the way through."""

import json

import pytest

from app.adapters import jsontext


def test_a_large_integer_keeps_every_digit() -> None:
    """A float would round this one, and the value is a customer id."""
    assert jsontext.compact('{"id": 10000000000000001}') == '{"id":10000000000000001}'


def test_a_decimal_keeps_the_text_it_arrived_as() -> None:
    assert jsontext.compact("[1.10, 2.0e3]") == "[1.10,2.0e3]"


def test_whitespace_is_removed_and_order_is_kept() -> None:
    compacted = jsontext.compact('{\n  "b": 1,\n  "a": [true, null]\n}')

    assert compacted == '{"b":1,"a":[true,null]}'


def test_non_ascii_text_stays_as_itself() -> None:
    assert jsontext.compact('{"city": "Rīga"}') == '{"city":"Rīga"}'


def test_a_quote_inside_a_string_is_escaped_again() -> None:
    assert jsontext.compact('["a \\"b\\""]') == '["a \\"b\\""]'


def test_a_number_loads_as_a_token_rather_than_a_number() -> None:
    loaded = jsontext.load("[1]")

    assert isinstance(loaded[0], jsontext.JsonNumber)
    assert loaded[0].text == "1"


def test_text_that_is_not_json_is_the_callers_problem() -> None:
    with pytest.raises(json.JSONDecodeError):
        jsontext.load("{oops}")


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_python_extensions_are_not_accepted_as_json(token: str) -> None:
    with pytest.raises(jsontext.NonStandardJson):
        jsontext.load(token)


def test_a_value_that_is_not_json_data_is_refused() -> None:
    with pytest.raises(TypeError):
        jsontext.encode(object())
