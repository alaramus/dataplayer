"""What a field tells the form about itself, beyond its type."""

from collections.abc import Iterator
from typing import Any

from app.adapters import registry
from app.adapters.cloud.accounts import METHODS
from app.adapters.layout import JSON_FILE, PEM_FILE, layout
from app.adapters.options import json_schema


def _properties(schema: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every property of a schema, its `$defs` and its variants included."""
    if isinstance(schema, dict):
        for name, value in (schema.get("properties") or {}).items():
            if isinstance(value, dict):
                yield name, value
        for value in schema.values():
            yield from _properties(value)
    elif isinstance(schema, list):
        for value in schema:
            yield from _properties(value)


def _every_schema() -> Iterator[dict[str, Any]]:
    for adapter_type in registry.all_types():
        yield json_schema(adapter_type.options_schema)
    for method in METHODS:
        yield method.model_json_schema()


def test_a_field_read_from_a_file_names_what_the_picker_offers() -> None:
    assert layout(multiline=True, file=PEM_FILE)["x-ui-file"] == ".pem,.crt,.cer,.key"
    assert "x-ui-file" not in layout(multiline=True)


def test_every_certificate_and_key_file_can_be_chosen_rather_than_pasted() -> None:
    """A PEM or a JSON key is a file somebody has; copying it by hand is the
    step the picker removes, so a new field of that kind must not miss it."""
    found: list[str] = []
    for schema in _every_schema():
        for name, prop in _properties(schema):
            description = str(prop.get("description", ""))
            title = str(prop.get("title", ""))
            if description.startswith("PEM"):
                assert prop.get("x-ui-file") == PEM_FILE, name
                found.append(name)
            elif title.endswith("(JSON)"):
                assert prop.get("x-ui-file") == JSON_FILE, name
                found.append(name)
    # A sweep that finds nothing proves nothing: the TLS block alone has three.
    assert {"tls_ca_certificate", "tls_client_certificate", "tls_client_key", "key_json"} <= set(
        found
    )
