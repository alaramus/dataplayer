"""An S3 store's objects as a storage for the explorer (D150, D379).

A node id is a key's path below the root, judged by the one containment rule;
a key no such id could name again is left out of a listing, as SFTP leaves out
a name the rule refuses. A folder is a common prefix, or the `name/` marker
the providers' consoles make for an empty one.

boto3 blocks, which is what a storage does (D151): every method runs in the
worker thread that asked, with no hop back to the loop.
"""

import io
import posixpath
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar

from botocore.exceptions import BotoCoreError, ClientError

from app.adapters.actions import ActionRefused
from app.adapters.explorer.copies import TooLargeToCopy, copies
from app.adapters.explorer.storage import (
    REMOTE_SEARCH,
    ROOT,
    Entry,
    Incoming,
    PathPlaces,
    Place,
    VersionChanged,
    is_plain_name,
)
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.s3.client import (
    client_for,
    error_code,
    identity_of,
    is_missing,
    reduced,
    status_of,
)
from app.adapters.s3.options import DEFAULT_REGION, S3Options
from app.adapters.s3.uploads import PART_BYTES, Upload
from app.core.translation import say

if TYPE_CHECKING:
    from types_boto3_s3.client import S3Client

T = TypeVar("T")

# A ranged GET costs a round trip, so a header reader's seeks are served from
# a quarter of a megabyte rather than SFTP's 64 KB.
READ_BUFFER = 256 * 1024

# What one action may touch, key by key: a store has no rename of a folder,
# so moving one is a request per object (D380).
MAX_OBJECTS = 10_000
# DeleteObjects takes a thousand keys at a time.
DELETE_BATCH = 1000
# CopyObject's own ceiling; above it a copy is made of parts.
LARGEST_SINGLE_COPY = 5 * 1024 * 1024 * 1024


class S3Storage(PathPlaces):
    search_limits = REMOTE_SEARCH

    def __init__(self, options: S3Options) -> None:
        self._options = options
        self._client = client_for(options)
        # Whose copies these are: the store, the key and where it stands.
        self._owner = f"s3:{identity_of(options)}"

    # --- where a node is ---------------------------------------------------------

    def place(self, node_id: str | None) -> Place:
        path = self.relative_path(node_id)
        if (
            self._options.bucket == ""
            and path.parts
            and not _bucket_name(path.parts[0])
        ):
            raise ValueError(
                say("Path outside the connector root: {node_id}", node_id=node_id)
            )
        return self.place_at(path)

    def unlinked_place(self, node_id: str) -> Place:
        # A store has no links.
        return self.place(node_id)

    def _address(self, place: Place) -> tuple[str | None, str]:
        """The bucket and the key a place is; the key of a folder has no slash
        at its end, and a bucket's own is empty."""
        parts = self.path_at(place).parts
        if self._options.bucket == "":
            if not parts:
                return None, ""
            return parts[0], "/".join(parts[1:])
        return self._options.bucket, "/".join((*_parts(self._options.prefix), *parts))

    def holds_buckets(self, place: Place) -> bool:
        return self._options.bucket == "" and place == ROOT

    def is_bucket(self, place: Place) -> bool:
        return self._options.bucket == "" and len(self.path_at(place).parts) == 1

    # --- asking the store ---------------------------------------------------------

    def _asked(self, work: Callable[[S3Client], T]) -> T:
        try:
            return work(self._client)
        except ClientError as failure:
            if status_of(failure) == 412 or error_code(failure) in _CONFLICTS:
                raise _PreconditionFailed from None
            if failure.operation_name in _CONDITIONAL_WRITES and (
                status_of(failure) == 501 or error_code(failure) == "NotImplemented"
            ):
                raise _ConditionsUnsupported from None
            if is_missing(failure):
                raise FileNotFoundError(say("That is no longer in the store")) from None
            raise reduced(failure) from None
        except BotoCoreError as failure:
            if is_missing(failure):
                raise FileNotFoundError(say("That is no longer in the store")) from None
            raise reduced(failure) from None

    def check(self) -> ConnectionCheckResult:
        def work(client: S3Client) -> None:
            if self._options.bucket == "":
                client.list_buckets()
            else:
                client.head_bucket(Bucket=self._options.bucket)

        try:
            self._asked(work)
        except FileNotFoundError:
            return ConnectionCheckResult(
                ok=False,
                message=say("There is no such bucket in this store"),
                error_kind="config",
            )
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        return ConnectionCheckResult(ok=True, message=say("Connection successful"))

    # --- what is there -------------------------------------------------------------

    def entry(self, place: Place) -> Entry | None:
        if place == ROOT:
            return Entry(place=ROOT, is_directory=True, size_bytes=0, modified_at=None)
        bucket, key = self._address(place)
        assert bucket is not None
        if self.is_bucket(place):
            # Looked up among the buckets listed rather than asked by HEAD,
            # which answers a name no bucket may have with a 400.
            listed = self._asked(lambda client: client.list_buckets())
            names = {str(found.get("Name", "")) for found in listed.get("Buckets", [])}
            return _folder(place) if bucket in names else None
        try:
            head = self._asked(
                lambda client: client.head_object(Bucket=bucket, Key=key)
            )
        except FileNotFoundError:
            head = None
        if head is not None:
            return Entry(
                place=place,
                is_directory=False,
                size_bytes=int(head.get("ContentLength", 0)),
                modified_at=head.get("LastModified"),
            )
        try:
            below = self._asked(
                lambda client: client.list_objects_v2(
                    Bucket=bucket, Prefix=f"{key}/", MaxKeys=1
                )
            )
        except FileNotFoundError:
            return None
        return _folder(place) if below.get("KeyCount", 0) > 0 else None

    def entries(self, place: Place) -> list[Entry]:
        bucket, key = self._address(place)
        if bucket is None:
            listed = self._asked(lambda client: client.list_buckets())
            return [
                Entry(
                    place=self.child(ROOT, name),
                    is_directory=True,
                    size_bytes=0,
                    modified_at=None,
                    created_at=found.get("CreationDate"),
                )
                for found in listed.get("Buckets", [])
                if _bucket_name(name := str(found.get("Name", "")))
            ]
        prefix = f"{key}/" if key else ""
        files: dict[str, Entry] = {}
        folders: dict[str, Entry] = {}
        for page in self._pages(bucket, prefix, delimiter="/"):
            for common in page.get("CommonPrefixes", []):
                name = str(common.get("Prefix", ""))[len(prefix) : -1]
                if is_plain_name(name):
                    folders[name] = _folder(self.child(place, name))
            for item in page.get("Contents", []):
                name = str(item.get("Key", ""))[len(prefix) :]
                # The folder's own marker is not one of its entries.
                if name == "" or not is_plain_name(name):
                    continue
                files[name] = Entry(
                    place=self.child(place, name),
                    is_directory=False,
                    size_bytes=int(item.get("Size", 0)),
                    modified_at=item.get("LastModified"),
                )
        if not files and not folders and place != ROOT and not self.is_bucket(place):
            # Nothing below may be an empty folder, or no folder at all.
            if self.entry(place) is None:
                raise FileNotFoundError(place.key)
        # An object and a prefix of one name: the object is what `entry`
        # finds, so the folder is left out, as a key the rule refuses is.
        folders = {name: found for name, found in folders.items() if name not in files}
        return [*folders.values(), *files.values()]

    def _pages(self, bucket: str, prefix: str, *, delimiter: str = "") -> Iterator[Any]:
        def first(client: S3Client) -> Iterator[Any]:
            paginator = client.get_paginator("list_objects_v2")
            arguments: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
            if delimiter:
                arguments["Delimiter"] = delimiter
            return iter(paginator.paginate(**arguments))

        pages = self._asked(first)
        while True:
            page = self._asked(lambda _client: next(pages, None))
            if page is None:
                return
            yield page

    def has_entries(self, place: Place) -> bool:
        # Claimed rather than asked, as SFTP does: a listing may hold two
        # thousand folders, and asking is a request for each.
        return True

    def version(self, place: Place) -> str:
        bucket, key = self._address(place)
        if bucket is None or key == "":
            raise FileNotFoundError(place.key)
        head = self._asked(lambda client: client.head_object(Bucket=bucket, Key=key))
        return str(head.get("ETag", ""))

    # --- reading -------------------------------------------------------------------

    def open(self, place: Place) -> BinaryIO:
        bucket, key = self._address(place)
        if bucket is None or key == "":
            raise FileNotFoundError(place.key)
        head = self._asked(lambda client: client.head_object(Bucket=bucket, Key=key))
        raw = _ObjectReader(self, bucket, key, int(head.get("ContentLength", 0)))
        return io.BufferedReader(raw, buffer_size=READ_BUFFER)

    def _range(self, bucket: str, key: str, start: int, end: int) -> bytes:
        answer = self._asked(
            lambda client: client.get_object(
                Bucket=bucket, Key=key, Range=f"bytes={start}-{end}"
            )
        )
        body = answer["Body"]
        try:
            return body.read()
        finally:
            body.close()

    @contextmanager
    def local_file(self, place: Place) -> Iterator[Path]:
        """A copy, or what the local disk would lend in its place, as SFTP
        lends one (D152)."""
        found = self.entry(place)
        if found is None or found.is_directory:
            with copies().scratch(self._owner) as folder:
                stand_in = folder / (place.name or "root")
                if found is not None:
                    stand_in.mkdir()
                yield stand_in
            return
        bucket, key = self._address(place)
        assert bucket is not None
        version = self.version(place)

        def fetch(target: Path) -> None:
            self._download(bucket, key, target)

        with copies().held(
            self._owner, place.key, place.name, version, found.size_bytes, fetch
        ) as path:
            yield path

    def local_root(self) -> Path:
        return copies().folder_of(self._owner)

    @contextmanager
    def local_tree(self, place: Place) -> Iterator[Path]:
        """Every key below a place fetched into a scratch folder, within what
        may pass through this server (D152)."""
        found = self.entry(place)
        with copies().scratch(self._owner) as folder:
            target = folder / (place.name or "root")
            if found is not None and not found.is_directory:
                if found.size_bytes > copies().largest_bytes:
                    raise TooLargeToCopy(place.name)
                bucket, key = self._address(place)
                assert bucket is not None
                self._download(bucket, key, target)
            elif found is not None:
                target.mkdir()
                for bucket, key, relative in self._below(place):
                    destination = target.joinpath(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if key.endswith("/"):
                        destination.mkdir(exist_ok=True)
                        continue
                    self._download(bucket, key, destination)
            yield target

    def _download(self, bucket: str, key: str, target: Path) -> None:
        def work(client: S3Client) -> None:
            client.download_file(bucket, key, str(target))

        self._asked(work)

    def _below(self, place: Place) -> Iterator[tuple[str, str, PurePosixPath]]:
        """Every key below a folder whose path the rule accepts, with its path
        below the folder, held to what may pass through here."""
        bucket, key = self._address(place)
        buckets = (
            [entry.name for entry in self.entries(ROOT)] if bucket is None else [bucket]
        )
        total = 0
        for name in buckets:
            prefix = f"{key}/" if bucket is not None and key else ""
            for page in self._pages(name, prefix):
                for item in page.get("Contents", []):
                    found = str(item.get("Key", ""))
                    rest = found[len(prefix) :]
                    parts = rest.removesuffix("/").split("/")
                    if rest == "" or not all(is_plain_name(part) for part in parts):
                        continue
                    total += int(item.get("Size", 0))
                    if total > copies().largest_bytes:
                        raise TooLargeToCopy(place.name or say("What came out"))
                    relative = PurePosixPath(*parts)
                    if bucket is None:
                        relative = PurePosixPath(name, relative)
                    yield name, found, relative

    # --- writing (D380) ------------------------------------------------------------

    @contextmanager
    def staged(self, near: Place, *, prefix: str = ".dataplayer-") -> Iterator[Path]:
        with copies().scratch(self._owner) as folder:
            staged = folder / f"{prefix}{uuid.uuid4().hex}"
            staged.touch()
            yield staged

    def publish(
        self,
        staged: Path,
        place: Place,
        *,
        replace: bool = False,
        expected_version: str | None = None,
    ) -> None:
        bucket, key = self._object(place)
        upload = Upload(self._asked, bucket, key)
        try:
            with staged.open("rb") as source:
                while chunk := source.read(PART_BYTES):
                    upload.write(chunk)
            self._finished(
                upload, place, replace=replace, expected_version=expected_version
            )
        except BaseException:
            upload.abort()
            raise
        self._forget(place)

    @contextmanager
    def incoming(
        self, near: Place, *, prefix: str = ".dataplayer-"
    ) -> Iterator[Incoming]:
        """Sent to the key it is going to as it arrives (D168). Every caller
        publishes where it said it was going; one that does not gets a copy
        on the server and the first key removed."""
        bucket, key = self._object(near)
        arriving = _Arriving(self, near, Upload(self._asked, bucket, key))
        try:
            yield arriving
        finally:
            arriving.discard()

    @contextmanager
    def filled(self, place: Place) -> Iterator[Path]:
        with copies().scratch(self._owner) as folder:
            yield folder
            files = [path for path in folder.rglob("*") if path.is_file()]
            if sum(path.stat().st_size for path in files) > copies().largest_bytes:
                raise TooLargeToCopy(place.name or say("What came out"))
            for path in sorted(folder.rglob("*")):
                relative = path.relative_to(folder)
                target = place
                for part in relative.parts:
                    target = self.child(target, part)
                if path.is_dir():
                    if not any(path.iterdir()):
                        self._marker(target)
                    continue
                with self.staged(target) as staged:
                    staged.write_bytes(path.read_bytes())
                    self.publish(staged, target, replace=True)

    def make_directory(self, place: Place) -> None:
        if self.entry(place) is not None:
            # Asked first for a bucket too: in us-east-1, and on RustFS, making
            # one the key already owns answers success.
            raise FileExistsError(place.key)
        if self.is_bucket(place):
            self._make_bucket(place.name)
            return
        self._marker(place, claim=True)

    def make_file(self, place: Place) -> None:
        if self.entry(place) is not None:
            raise FileExistsError(place.key)
        bucket, key = self._object(place)
        upload = Upload(self._asked, bucket, key)
        self._finished(upload, place, replace=False, expected_version=None)
        self._forget(place)

    def rename(self, place: Place, to: Place) -> None:
        """A copy on the server and the original removed: a store cannot
        rename. Not atomic, and said so (D380). A bucket moved into a folder
        is emptied into it and then deleted (D381)."""
        self._refuse_into_bucket(to)
        if self.entry(to) is not None:
            raise FileExistsError(to.key)
        bucket = self.is_bucket(place)
        if bucket:
            # Before anything is copied: a bucket that keeps versions could
            # not be deleted at the end.
            self._refuse_kept_versions(place.name)
        moved = self._copied(place, to)
        self._deleted(moved)
        if bucket:
            self._asked(lambda client: client.delete_bucket(Bucket=place.name))
        self._forget(place)

    def copy(self, place: Place, to: Place) -> None:
        """A folder or a whole bucket copied below a folder, on the server; a
        bucket's copy is a folder of its name (D381)."""
        self._refuse_into_bucket(to)
        if self.entry(to) is not None:
            raise FileExistsError(to.key)
        self._copied(place, to)

    def remove(self, place: Place) -> None:
        if place == ROOT:
            raise PermissionError(place.key)
        if self.is_bucket(place):
            self._remove_bucket(place)
            return
        found = self.entry(place)
        if found is None:
            raise FileNotFoundError(place.key)
        bucket, key = self._object(place)
        if found.is_directory:
            self._deleted(
                [(bucket, item) for item in self._keys(bucket, f"{key}/", place)]
            )
        else:
            self._deleted([(bucket, key)])
        self._forget(place)

    def remove_empty(self, place: Place) -> None:
        bucket, key = self._address(place)
        if bucket is None:
            raise PermissionError(place.key)
        if self.is_bucket(place):
            try:
                self._asked(lambda client: client.delete_bucket(Bucket=bucket))
            except AdapterError:
                raise OSError(place.key) from None
            return
        marker = f"{key}/"
        listed = self._asked(
            lambda client: client.list_objects_v2(
                Bucket=bucket, Prefix=marker, MaxKeys=2
            )
        )
        if any(
            str(item.get("Key", "")) != marker for item in listed.get("Contents", [])
        ):
            raise OSError(place.key)
        self._deleted([(bucket, marker)])
        self._forget(place)

    # --- what writing is made of ---------------------------------------------------

    def _object(self, place: Place) -> tuple[str, str]:
        """The bucket and key of an object; none at the root, nor at a
        bucket's place when the root lists buckets."""
        bucket, key = self._address(place)
        if bucket is None or key == "" or self.is_bucket(place):
            raise ActionRefused(
                "not_applicable", say("Only buckets are kept at the root of the store")
            )
        return bucket, key

    def _finished(
        self,
        upload: Upload,
        place: Place,
        *,
        replace: bool,
        expected_version: str | None,
    ) -> None:
        """Put in place under the condition the write asks for, or by asking
        first where the store does not take conditions."""
        if not replace and self._is_folder(place):
            raise FileExistsError(place.key)
        conditions: dict[str, str] = {}
        if not replace:
            conditions = {"IfNoneMatch": "*"}
        elif expected_version is not None:
            conditions = {"IfMatch": expected_version}
        try:
            upload.finish(conditions)
        except _PreconditionFailed:
            if replace:
                raise VersionChanged from None
            raise FileExistsError(place.key) from None
        except _ConditionsUnsupported:
            current = self._version_or_none(place)
            if not replace and current is not None:
                raise FileExistsError(place.key) from None
            if expected_version is not None and current != expected_version:
                raise VersionChanged from None
            upload.finish({})

    def _is_folder(self, place: Place) -> bool:
        found = self.entry(place)
        return found is not None and found.is_directory

    def _version_or_none(self, place: Place) -> str | None:
        try:
            return self.version(place)
        except FileNotFoundError:
            return None

    def _marker(self, place: Place, *, claim: bool = False) -> None:
        bucket, key = self._object(place)
        upload = Upload(self._asked, bucket, f"{key}/")
        try:
            upload.finish({"IfNoneMatch": "*"} if claim else {})
        except _PreconditionFailed:
            raise FileExistsError(place.key) from None
        except _ConditionsUnsupported:
            upload.finish({})

    def _keys(self, bucket: str, prefix: str, place: Place) -> list[str]:
        """Every key below a prefix, held to what one action may touch."""
        found: list[str] = []
        for page in self._pages(bucket, prefix):
            for item in page.get("Contents", []):
                found.append(str(item.get("Key", "")))
                if len(found) > MAX_OBJECTS:
                    raise ActionRefused(
                        "too_large",
                        say(
                            "{name} holds more than {count} objects; this store "
                            "changes them one by one, so it is refused",
                            name=place.name,
                            count=MAX_OBJECTS,
                        ),
                    )
        return found

    def _copied(self, place: Place, to: Place) -> list[tuple[str, str]]:
        """Every key of a place copied below another, on the server; the keys
        copied from, for a move to remove."""
        found = self.entry(place)
        if found is None:
            raise FileNotFoundError(place.key)
        bucket, key = (
            (place.name, "") if self.is_bucket(place) else self._object(place)
        )
        target_bucket, target_key = self._object(to)
        if not found.is_directory:
            self._copy_object(bucket, key, target_bucket, target_key)
            return [(bucket, key)]
        below = f"{key}/" if key else ""
        keys = self._keys(bucket, below, place)
        for source in keys:
            self._copy_object(
                bucket, source, target_bucket, f"{target_key}/{source[len(below) :]}"
            )
        if not keys:
            self._marker(to)
        return [(bucket, source) for source in keys]

    def _copy_object(self, bucket: str, key: str, to_bucket: str, to_key: str) -> None:
        source: Any = {"Bucket": bucket, "Key": key}
        head = self._asked(lambda client: client.head_object(Bucket=bucket, Key=key))
        if int(head.get("ContentLength", 0)) <= LARGEST_SINGLE_COPY:
            self._asked(
                lambda client: client.copy_object(
                    Bucket=to_bucket, Key=to_key, CopySource=source
                )
            )
        else:
            # Above 5 GB a copy is made of parts; still on the server.
            self._asked(lambda client: client.copy(source, to_bucket, to_key))

    def _deleted(self, keys: list[tuple[str, str]]) -> None:
        by_bucket: dict[str, list[str]] = {}
        for bucket, key in keys:
            by_bucket.setdefault(bucket, []).append(key)
        for bucket, names in by_bucket.items():
            for start in range(0, len(names), DELETE_BATCH):
                self._delete_batch(bucket, names[start : start + DELETE_BATCH])

    def _delete_batch(self, bucket: str, names: list[str]) -> None:
        batch: Any = {"Objects": [{"Key": name} for name in names], "Quiet": True}

        def work(client: S3Client) -> Any:
            return client.delete_objects(Bucket=bucket, Delete=batch)

        if self._asked(work).get("Errors"):
            raise OSError(say("The store did not delete every object"))

    def _refuse_into_bucket(self, to: Place) -> None:
        """S3 has no call that renames a bucket or makes one by copying."""
        if self.is_bucket(to):
            raise ActionRefused(
                "not_applicable",
                say("A bucket cannot be renamed, nor made by a copy or a move"),
            )

    # --- buckets (D381) ---------------------------------------------------------------

    def _make_bucket(self, name: str) -> None:
        if not _new_bucket_name(name):
            raise ActionRefused(
                "not_applicable",
                say(
                    "A bucket's name is 3 to 63 lowercase letters, digits, dots "
                    "and hyphens, beginning and ending with a letter or a digit"
                ),
            )
        region = self._options.region_name
        arguments: dict[str, Any] = {"Bucket": name}
        if region != DEFAULT_REGION:
            arguments["CreateBucketConfiguration"] = {"LocationConstraint": region}
        try:
            self._client.create_bucket(**arguments)
        except ClientError as failure:
            if error_code(failure) in (
                "BucketAlreadyOwnedByYou",
                "BucketAlreadyExists",
            ):
                raise FileExistsError(name) from None
            raise reduced(failure) from None
        except BotoCoreError as failure:
            raise reduced(failure) from None

    def _remove_bucket(self, place: Place) -> None:
        bucket = place.name
        self._refuse_kept_versions(bucket)
        self._deleted([(bucket, key) for key in self._keys(bucket, "", place)])
        self._asked(lambda client: client.delete_bucket(Bucket=bucket))
        self._forget(place)

    def _refuse_kept_versions(self, bucket: str) -> None:
        versioning = self._asked(
            lambda client: client.get_bucket_versioning(Bucket=bucket)
        )
        if versioning.get("Status") in ("Enabled", "Suspended"):
            versions = self._asked(
                lambda client: client.list_object_versions(Bucket=bucket, MaxKeys=1)
            )
            if versions.get("Versions") or versions.get("DeleteMarkers"):
                raise ActionRefused(
                    "not_applicable",
                    say(
                        "{name} keeps old versions of its objects; empty it with "
                        "a lifecycle rule, then delete it",
                        name=bucket,
                    ),
                )

    def _forget(self, place: Place) -> None:
        """The copies of a node just written, and of everything below it."""
        copies().forget(
            self._owner,
            lambda key: self.contains(
                place, Place(key=key, name=posixpath.basename(key))
            ),
        )


# A conditional write that lost: the version moved, or another write of the
# same key was under way.
_CONFLICTS = ("PreconditionFailed", "ConditionalRequestConflict")
_CONDITIONAL_WRITES = ("PutObject", "CompleteMultipartUpload")


class _PreconditionFailed(Exception):
    """A conditional write found the name taken, or the version changed."""


class _ConditionsUnsupported(Exception):
    """A store that does not take If-None-Match or If-Match on a write."""


class _Arriving:
    """A file on its way into the store, sent as it arrives."""

    def __init__(self, storage: S3Storage, near: Place, upload: Upload) -> None:
        self._storage = storage
        self._near = near
        self._upload = upload
        self._published = False

    def write(self, data: bytes) -> None:
        self._upload.write(data)

    def publish(self, place: Place, *, replace: bool = False) -> None:
        storage = self._storage
        if place == self._near:
            storage._finished(
                self._upload, place, replace=replace, expected_version=None
            )
        else:
            # Completed where it was going, then moved: no caller does this.
            storage._finished(
                self._upload, self._near, replace=True, expected_version=None
            )
            if not replace and storage.entry(place) is not None:
                storage.remove(self._near)
                raise FileExistsError(place.key)
            bucket, key = storage._object(self._near)
            target_bucket, target_key = storage._object(place)
            storage._copy_object(bucket, key, target_bucket, target_key)
            storage._deleted([(bucket, key)])
        self._published = True
        storage._forget(place)

    def discard(self) -> None:
        if not self._published:
            self._upload.abort()


class _ObjectReader(io.RawIOBase):
    """An object read by ranged GETs, at any offset, from a worker thread."""

    def __init__(self, storage: S3Storage, bucket: str, key: str, size: int) -> None:
        super().__init__()
        self._storage = storage
        self._bucket = bucket
        self._key = key
        self._size = size
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]  # io's own signature takes a writable buffer
        if self._position >= self._size or len(buffer) == 0:
            return 0
        end = min(self._position + len(buffer), self._size) - 1
        data = self._storage._range(self._bucket, self._key, self._position, end)
        buffer[: len(data)] = data
        self._position += len(data)
        return len(data)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._size}[
            whence
        ]
        self._position = max(0, base + offset)
        return self._position

    def tell(self) -> int:
        return self._position


def _folder(place: Place) -> Entry:
    return Entry(place=place, is_directory=True, size_bytes=0, modified_at=None)


def _parts(prefix: str) -> tuple[str, ...]:
    return tuple(part for part in prefix.split("/") if part)


def _bucket_name(name: str) -> bool:
    """A name a bucket may have had, the old rules included: an id whose first
    segment is anything else names nothing in this store."""
    return 1 <= len(name) <= 255 and is_plain_name(name)


def _new_bucket_name(name: str) -> bool:
    """The rules a new bucket's name is held to everywhere (D381), checked
    before anything is sent."""
    return (
        3 <= len(name) <= 63
        and all(char in _BUCKET_CHARACTERS for char in name)
        and name[0].isalnum()
        and name[-1].isalnum()
        and ".." not in name
        and not all(part.isdigit() for part in name.split("."))
    )


_BUCKET_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-")
