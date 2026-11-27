"""HashiCorp Vault as the provider of a `vault` account's secrets (D454).

Spoken to over Vault's HTTP API with `requests`, so no client library is
installed; registered for the kind on import, which `app.adapters` does.
"""

from app.adapters.cloud import register_issuer
from app.adapters.cloud.vault.issuer import VaultIssuer

register_issuer("vault", VaultIssuer())
