"""What an options schema says, asked in one place.

A source type used to describe its options with a single model, and every
consumer reached for `model_json_schema` and `model_fields` on it directly.
A type whose fields depend on the way it is connected to describes them with a
discriminated union instead, and a union is `Annotated[A | B, ...]`: it has
neither of those attributes. Rather than teach every consumer the difference,
the question is asked here.

`TypeAdapter` is what makes one answer serve both: it validates and produces a
JSON Schema for a bare model and for a union alike.

`secret_field_names` lives here for the same reason, and it is the reason that
matters most: D4 says which values are encrypted is read off the declaration
rather than kept in a list, and a field declared `SecretStr` by one variant
only must still reach the encrypted blob.
"""

from collections.abc import Mapping
from typing import Any, get_args

from pydantic import BaseModel, SecretStr, TypeAdapter

# Either a model class or a discriminated union of them. `Any` because the
# second has no type that mypy can name: `Annotated[A | B, FieldInfo]` is a
# value, not a class, so `type[BaseModel]` excludes it and there is nothing
# narrower to put in its place. The alias exists so that every signature below
# says which of the two it means.
type OptionsSchema = Any

# TypeAdapter builds a validator and a schema on construction, and both are
# asked for on the path of an ordinary request. Keyed by identity rather than
# by equality: a schema is a module-level object, and a FieldInfo inside an
# Annotated union is not hashable, so a dict cannot hold one as a key.
_adapters: list[tuple[OptionsSchema, TypeAdapter[Any]]] = []


def _adapter_for(schema: OptionsSchema) -> TypeAdapter[Any]:
    for known, adapter in _adapters:
        if known is schema:
            return adapter
    adapter = TypeAdapter(schema)
    _adapters.append((schema, adapter))
    return adapter


def json_schema(schema: OptionsSchema) -> dict[str, Any]:
    """The JSON Schema a client builds the form from.

    A union arrives as `$defs` plus `oneOf` plus a `discriminator`; a plain
    model as its own properties. The client reads both — see `readSchema`.
    """
    return _adapter_for(schema).json_schema()


def validate(schema: OptionsSchema, data: Mapping[str, Any]) -> BaseModel:
    """Options as the model that declared them.

    For a union this picks the variant the discriminator names, and rejects an
    object that carries no discriminator at all.
    """
    validated: BaseModel = _adapter_for(schema).validate_python(data)
    return validated


def variants(schema: OptionsSchema) -> list[type[BaseModel]]:
    """The models a schema may turn out to be, in declaration order.

    One of them for a plain model, so a caller never has to ask which kind of
    schema it is holding.
    """
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return [schema]

    # `Annotated[A | B, FieldInfo]` unwraps to `(A | B, FieldInfo)`, and
    # `A | B` to `(A, B)`; anything that is not a model contributes nothing.
    found: list[type[BaseModel]] = []
    for argument in get_args(schema):
        found.extend(variants(argument))
    return found


def secret_field_names(schema: OptionsSchema) -> set[str]:
    """Names of fields declared as SecretStr, across every variant.

    The single source of truth about which values are encrypted: there is no
    separate list of secret fields, so a field cannot be left out by mistake.
    The union rather than the intersection — a field that is a secret anywhere
    is a secret.
    """
    return {
        name
        for variant in variants(schema)
        for name, field in variant.model_fields.items()
        if field.annotation is SecretStr
    }


# What a field holding a key id says it is for, so the form offers the owner's
# keys and the store can find the connections that use one.
KEY_REFERENCE = "ssh-key"


def key_reference_names(schema: OptionsSchema) -> set[str]:
    """Names of fields that hold the id of one of the owner's SSH keys.

    Read off the declaration for the reason secrets are: a store that has to
    refuse deleting a key a connection still signs in with (D146) would
    otherwise keep a list of which option of which source names a key.
    """
    return _named_for(schema, KEY_REFERENCE)


# What a field holding the one server key a connection trusts says it is for
# (D145), so the form fetches and compares, and a service this server started
# can have its key pinned without a list of which source keeps it where (D153).
SERVER_KEY = "ssh-host-key"


def server_key_names(schema: OptionsSchema) -> set[str]:
    """Names of fields that hold the server key a connection has pinned."""
    return _named_for(schema, SERVER_KEY)


def _named_for(schema: OptionsSchema, purpose: str) -> set[str]:
    return {
        name
        for variant in variants(schema)
        for name, field in variant.model_fields.items()
        if isinstance(field.json_schema_extra, dict)
        and field.json_schema_extra.get("x-ui-purpose") == purpose
    }
