"""An S3 store as a source: the file explorer over its objects (D150, D379).

Everything the file source does is the explorer's and comes with it; what is
here is the store: how it is reached, which actions it offers, its address
and the cards it shows (D382).
"""

from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import quote, unquote, urlsplit

from app.adapters.explorer.actions import (
    EXPLORER_ACTION_TYPES,
    ConnectFolder,
    ExplorerActionType,
)
from app.adapters.explorer.explorer import Explorer
from app.adapters.registry import AdapterContext, CatalogFace, register
from app.adapters.s3.options import S3Options
from app.adapters.s3.storage import S3Storage
from app.core.translation import N_, say

# `bucket.s3.region.amazonaws.com`, `bucket.s3.amazonaws.com`, and the same
# with a dash before the region, which older regions still answer to.
_AWS_SUFFIX = ".amazonaws.com"


class S3Adapter(Explorer):
    """The explorer over one bucket, or over every bucket a key may list."""

    # A folder never becomes a connection of its own: the draft would carry
    # the key to the browser, as an SSH folder's would carry its password.
    explorer_action_types: ClassVar[tuple[ExplorerActionType, ...]] = tuple(
        action_type
        for action_type in EXPLORER_ACTION_TYPES
        if action_type is not ConnectFolder
    )

    def __init__(self, options: S3Options, context: AdapterContext) -> None:
        self._options = options
        super().__init__(S3Storage(options))

    def connection_string(self) -> str:
        value = self.draft_connection_string(self._options.model_dump(mode="python"))
        return value or "s3://"

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        """Where the objects are, as one line, and never with a key (D382):
        `s3://bucket/folder` on Amazon S3, the path-style URL elsewhere."""
        endpoint = _text(options.get("endpoint")).rstrip("/")
        bucket = _text(options.get("bucket"))
        prefix = _text(options.get("prefix")).strip("/")
        path = "/".join(
            quote(part, safe="") for part in (bucket, *prefix.split("/")) if part
        )
        if endpoint != "":
            return f"{endpoint}/{path}" if path else endpoint
        return f"s3://{path}" if bucket else None

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        """The endpoint, region, bucket and folder an address states; the keys
        are typed apart, as an SSH password is."""
        try:
            parts = urlsplit(url.strip())
            port = parts.port
        except ValueError:
            raise ValueError(say("That is not an S3 address")) from None
        if (
            parts.scheme not in ("s3", "http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query != ""
            or parts.fragment != ""
        ):
            raise ValueError(say("That is not an S3 address"))
        segments = [unquote(part) for part in parts.path.split("/") if part]
        if parts.scheme == "s3":
            return _located(unquote(parts.hostname), segments)
        host = parts.hostname.lower()
        if host.endswith(_AWS_SUFFIX):
            return _on_aws(host, segments)
        origin = f"{parts.scheme}://{host}" + (f":{port}" if port is not None else "")
        found = _located(segments[0], segments[1:]) if segments else {}
        return {
            "endpoint": origin,
            **({"addressing": "path"} if segments else {}),
            **found,
        }


def _on_aws(host: str, segments: list[str]) -> dict[str, Any]:
    """An Amazon S3 address, virtual-hosted or path-style."""
    labels = host.removesuffix(_AWS_SUFFIX).split(".")
    if "s3" not in labels and not any(label.startswith("s3-") for label in labels):
        raise ValueError(say("That is not an S3 address"))
    at = next(
        i for i, label in enumerate(labels) if label == "s3" or label.startswith("s3-")
    )
    region = (
        labels[at][3:] if labels[at].startswith("s3-") else ".".join(labels[at + 1 :])
    )
    found: dict[str, Any] = {"endpoint": ""}
    if region:
        found["region"] = region
    bucket = ".".join(labels[:at])
    if bucket:
        return {**found, **_located(bucket, segments)}
    return {**found, **(_located(segments[0], segments[1:]) if segments else {})}


def _located(bucket: str, folder: list[str]) -> dict[str, Any]:
    found: dict[str, Any] = {"bucket": bucket}
    if folder:
        found["prefix"] = "/".join(folder)
    return found


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


@register(
    name="s3",
    title=N_("S3"),
    category="files",
    description=N_(
        "Amazon S3 or a store that speaks its API. Browse buckets and folders "
        "and work with objects as with your own files: tables, SQL over files, "
        "the editor, archives, search and copying between connections. Buckets "
        "are made and deleted here too. Signs in with an access key."
    ),
    options_schema=S3Options,
    adapter_class=S3Adapter,
    # One form for every store that speaks S3 (D382): a card fills in what
    # its provider always names the same and says where the rest is. None
    # starts anything.
    faces=(
        CatalogFace(
            key="s3",
            title=N_("Amazon S3"),
            note=N_(
                "Sign in with an IAM user's access key. The region is the "
                "bucket's, such as eu-central-1."
            ),
            note_link="https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html",
        ),
        CatalogFace(
            key="minio",
            title=N_("MinIO"),
            options={"addressing": "path"},
            note=N_(
                "The server's S3 address, usually http://host:9000, and an "
                "access key made in its console."
            ),
            note_link="https://docs.min.io/",
        ),
        CatalogFace(
            key="cloudflare-r2",
            title=N_("Cloudflare R2"),
            options={"region": "auto", "addressing": "path"},
            note=N_(
                "The endpoint is https://<account id>.r2.cloudflarestorage.com. "
                "Make an R2 API token; its access key and secret are the keys here."
            ),
            note_link="https://developers.cloudflare.com/r2/api/tokens/",
        ),
        CatalogFace(
            key="backblaze-b2",
            title=N_("Backblaze B2"),
            note=N_(
                "The endpoint is the bucket's S3 endpoint, such as "
                "https://s3.us-west-004.backblazeb2.com, and the region its "
                "middle part. Sign in with an application key."
            ),
            note_link="https://www.backblaze.com/docs/cloud-storage-s3-compatible-api",
        ),
        CatalogFace(
            key="wasabi",
            title=N_("Wasabi"),
            note=N_(
                "The endpoint names the bucket's region, such as "
                "https://s3.eu-central-1.wasabisys.com, and so does the region."
            ),
            note_link="https://docs.wasabi.com/docs/what-are-the-service-urls-for-wasabi-s-different-storage-regions",
        ),
        CatalogFace(
            key="digitalocean-spaces",
            title=N_("DigitalOcean Spaces"),
            note=N_(
                "The endpoint is the region's, such as "
                "https://fra1.digitaloceanspaces.com, and the region its first "
                "part. Sign in with a Spaces access key."
            ),
            note_link="https://docs.digitalocean.com/products/spaces/how-to/manage-access/",
        ),
        CatalogFace(
            key="gcs",
            title=N_("Google Cloud Storage"),
            options={"endpoint": "https://storage.googleapis.com", "region": "auto"},
            note=N_(
                "Through its S3-compatible API, with HMAC keys made under "
                "Settings, Interoperability. Service account sign-in is not "
                "supported."
            ),
            note_link="https://cloud.google.com/storage/docs/authentication/hmackeys",
        ),
        CatalogFace(
            key="yandex-object-storage",
            title=N_("Yandex Object Storage"),
            options={
                "endpoint": "https://storage.yandexcloud.net",
                "region": "ru-central1",
            },
            note=N_("Sign in with a service account's static access key."),
            note_link="https://yandex.cloud/en/docs/storage/s3/",
        ),
        CatalogFace(
            key="vk-cloud",
            title=N_("VK Cloud"),
            options={
                "endpoint": "https://hb.ru-msk.vkcloud-solutions.ru",
                "region": "ru-msk",
            },
            note=N_(
                "Sign in with an account's keys, made in the Object Storage section."
            ),
            note_link="https://cloud.vk.com/docs/en/storage/s3",
        ),
        CatalogFace(
            key="selectel",
            title=N_("Selectel"),
            note=N_(
                "The endpoint and region are the pool's, shown in the bucket's "
                "settings, such as https://s3.ru-1.storage.selcloud.ru and ru-1. "
                "Sign in with a service user's S3 keys."
            ),
            note_link="https://docs.selectel.ru/en/s3/",
        ),
        CatalogFace(
            key="hetzner",
            title=N_("Hetzner Object Storage"),
            note=N_(
                "The endpoint is the location's, such as "
                "https://fsn1.your-objectstorage.com, and the region is the "
                "location. Make S3 credentials in the project's Security section."
            ),
            note_link="https://docs.hetzner.com/storage/object-storage/",
        ),
    ),
)
def _build(options: S3Options, context: AdapterContext) -> S3Adapter:
    return S3Adapter(options, context)
