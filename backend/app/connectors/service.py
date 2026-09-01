import json
from typing import Any

from app.adapters import options as options_schema
from app.adapters.protocol import DataAdapter
from app.adapters.registry import AdapterContext, AdapterType
from app.core import crypto


def split_options(
    adapter_type: AdapterType, options: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    """Split options into non-secret configuration and encrypted secrets.

    The split follows the schema declaration — which fields are SecretStr —
    rather than a separate list, so a field cannot be left unmarked. When
    the schema is a union, that declaration is read across every variant.
    """
    model = options_schema.validate(adapter_type.options_schema, options)
    secret_names = options_schema.secret_field_names(adapter_type.options_schema)
    dumped = model.model_dump(mode="json")

    config = {name: value for name, value in dumped.items() if name not in secret_names}
    secrets = {
        name: getattr(model, name).get_secret_value()
        for name in secret_names
        # A secret name is collected across every variant of the schema, so
        # the one that was chosen need not carry all of them: a variant
        # without a password has nothing to encrypt.
        if getattr(model, name, None) is not None
    }
    return config, crypto.encrypt(json.dumps(secrets).encode(), purpose="connector")


def merge_options(config: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]:
    """Reassemble the full option set from configuration and secrets."""
    secrets = json.loads(crypto.decrypt(secrets_blob, purpose="connector"))
    return {**config, **secrets}


def fill_missing_secrets(
    adapter_type: AdapterType, options: dict[str, Any], secrets_blob: bytes
) -> dict[str, Any]:
    """Substitute stored secrets for the ones that were not supplied.

    Needed both by PATCH and by the connection check while editing: the user
    changes the port without retyping the password.
    """
    stored = json.loads(crypto.decrypt(secrets_blob, purpose="connector"))
    filled = dict(options)
    for name in options_schema.secret_field_names(adapter_type.options_schema):
        if not filled.get(name) and name in stored:
            filled[name] = stored[name]
    return filled


def build_adapter(
    adapter_type: AdapterType, options: dict[str, Any], context: AdapterContext
) -> DataAdapter:
    model = options_schema.validate(adapter_type.options_schema, options)
    return adapter_type.factory(model, context)
