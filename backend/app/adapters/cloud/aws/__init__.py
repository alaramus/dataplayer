"""Amazon Web Services as the provider of an `aws` account's secrets (D449, D453).

The one package outside S3's that imports boto3 (`.importlinter`). It is
registered for the kind on import, which `app.adapters` does.
"""

from app.adapters.cloud import register_issuer
from app.adapters.cloud.aws.issuer import AwsIssuer

register_issuer("aws", AwsIssuer())
