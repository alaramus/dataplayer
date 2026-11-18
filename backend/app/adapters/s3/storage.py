"""An S3 store's objects as a storage for the explorer (D150, D379).

A node id is a key's path below the root, judged by the one containment rule;
a key no such id could name again is left out of a listing, as SFTP leaves out
a name the rule refuses. A folder is a common prefix, or the `name/` marker
the providers' consoles make for an empty one.

boto3 blocks, which is what a storage does (D151): every method runs in the
worker thread that asked, with no hop back to the loop.
"""

import io
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar

from botocore.exceptions import BotoCoreError, ClientError

from app.adapters.explorer.copies import TooLargeToCopy, copies
from app.adapters.explorer.storage import (
    REMOTE_SEARCH,
    ROOT,
    Entry,
    Incoming,
    PathPlaces,
    Place,
    is_plain_name,
)
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.s3.client import client_for, identity_of, is_missing, reduced
from app.adapters.s3.options import S3Options
from app.core.translation import say

if TYPE_CHECKING:
    from types_boto3_s3.client import S3Client

T = TypeVar("T")

# A ranged GET costs a round trip, so a header reader's seeks are served from
# a quarter of a megabyte rather than SFTP's 64 KB.
READ_BUFFER = 256 * 1024


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

    def _is_bucket(self, place: Place) -> bool:
        return self._options.bucket == "" and len(self.path_at(place).parts) == 1

    # --- asking the store ---------------------------------------------------------

    def _asked(self, work: Callable[[S3Client], T]) -> T:
        try:
            return work(self._client)
        except (ClientError, BotoCoreError) as failure:
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
        if self._is_bucket(place):
            try:
                self._asked(lambda client: client.head_bucket(Bucket=bucket))
            except FileNotFoundError:
                return None
            return _folder(place)
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
        if not files and not folders and place != ROOT and not self._is_bucket(place):
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

    # --- writing: the next step ---------------------------------------------------

    @contextmanager
    def staged(self, near: Place, *, prefix: str = ".dataplayer-") -> Iterator[Path]:
        raise PermissionError(near.key)
        yield Path()  # pragma: no cover - a generator needs a yield

    def publish(
        self,
        staged: Path,
        place: Place,
        *,
        replace: bool = False,
        expected_version: str | None = None,
    ) -> None:
        raise PermissionError(place.key)

    @contextmanager
    def incoming(
        self, near: Place, *, prefix: str = ".dataplayer-"
    ) -> Iterator[Incoming]:
        raise PermissionError(near.key)
        yield  # pragma: no cover - a generator needs a yield

    @contextmanager
    def filled(self, place: Place) -> Iterator[Path]:
        raise PermissionError(place.key)
        yield Path()  # pragma: no cover - a generator needs a yield

    def make_directory(self, place: Place) -> None:
        raise PermissionError(place.key)

    def make_file(self, place: Place) -> None:
        raise PermissionError(place.key)

    def rename(self, place: Place, to: Place) -> None:
        raise PermissionError(place.key)

    def copy(self, place: Place, to: Place) -> None:
        raise PermissionError(place.key)

    def remove(self, place: Place) -> None:
        raise PermissionError(place.key)

    def remove_empty(self, place: Place) -> None:
        raise PermissionError(place.key)


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
