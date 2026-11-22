import pytest

from app.adapters.content import JsonContent, JsonObject, JsonScalar
from app.adapters.rabbitmq.content import MAX_JSON_BYTES, json_document


def test_management_json_keeps_its_tree_and_lexical_numbers() -> None:
    content = json_document(b'{"name":"orders","offset":10000000000000001}')

    assert isinstance(content, JsonContent)
    assert isinstance(content.value, JsonObject)
    values = {entry.name: entry.value for entry in content.value.entries}
    assert isinstance(values["offset"], JsonScalar)
    assert values["offset"].value == "10000000000000001"
    assert not content.truncated


def test_a_management_document_over_four_megabytes_has_only_a_bounded_preview() -> None:
    body = b'{"value":"' + b"x" * MAX_JSON_BYTES + b'"}'

    content = json_document(body)

    assert isinstance(content, JsonContent)
    assert content.value is None
    assert content.source_text is not None
    assert len(content.source_text.encode("utf-8")) <= MAX_JSON_BYTES
    assert content.truncated
    assert content.notice == "This JSON document is larger than 4 MB"


def test_an_invalid_management_json_document_is_rejected() -> None:
    with pytest.raises(ValueError):
        json_document(b'{"name":')
