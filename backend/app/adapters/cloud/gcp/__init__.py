"""Google Cloud as the provider of a `gcp` account's secrets (D449, D453, D455).

The one package that imports google-auth (`.importlinter`); registered for the
kind on import, which `app.adapters` does.
"""

from app.adapters.cloud import register_issuer
from app.adapters.cloud.gcp.issuer import GcpIssuer

register_issuer("gcp", GcpIssuer())
