import json
from typing import Any

from app.adapters.protocol import DataAdapter
from app.adapters.registry import AdapterContext, AdapterType, secret_field_names
from app.core import crypto


def split_options(
    adapter_type: AdapterType, options: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    """Split options into non-secret configuration and encrypted secrets.

    The split follows the schema declaration — which fields are SecretStr —
    rather than a separate list, so a field cannot be left unmarked.
    """
    model = adapter_type.options_schema.model_validate(options)
    secret_names = secret_field_names(adapter_type.options_schema)
    dumped = model.model_dump(mode="json")

    config = {name: value for name, value in dumped.items() if name not in secret_names}
    secrets = {
        name: getattr(model, name).get_secret_value()
        for name in secret_names
        if getattr(model, name) is not None
    }
    return config, crypto.encrypt(json.dumps(secrets).encode())


def merge_options(config: dict[str, Any], secrets_blob: bytes) -> dict[str, Any]:
    """Reassemble the full option set from configuration and secrets."""
    secrets = json.loads(crypto.decrypt(secrets_blob))
    return {**config, **secrets}


def fill_missing_secrets(
    adapter_type: AdapterType, options: dict[str, Any], secrets_blob: bytes
) -> dict[str, Any]:
    """Substitute stored secrets for the ones that were not supplied.

    Needed both by PATCH and by the connection check while editing: the user
    changes the port without retyping the password.
    """
    stored = json.loads(crypto.decrypt(secrets_blob))
    filled = dict(options)
    for name in secret_field_names(adapter_type.options_schema):
        if not filled.get(name) and name in stored:
            filled[name] = stored[name]
    return filled


def build_adapter(
    adapter_type: AdapterType, options: dict[str, Any], context: AdapterContext
) -> DataAdapter:
    model = adapter_type.options_schema.model_validate(options)
    return adapter_type.factory(model, context)
