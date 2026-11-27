"""Microsoft Azure as the provider of an `azure` account's secrets (D449, D453).

The one package that imports azure-identity and msal (`.importlinter`);
registered for the kind on import, which `app.adapters` does.
"""

from app.adapters.cloud import register_issuer
from app.adapters.cloud.azure.issuer import AzureIssuer

register_issuer("azure", AzureIssuer())
