"""A store that refuses If-None-Match and If-Match on a write (D380): asked
first instead, without a store."""

from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.adapters.explorer.storage import VersionChanged
from app.adapters.s3.options import S3Options
from app.adapters.s3.storage import S3Storage


def _failure(code: str, status: int, operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        operation,
    )


class _OldStore:
    """Takes a plain PUT and answers 501 to a conditional one."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, **conditions: str
    ) -> Any:
        if conditions:
            raise _failure("NotImplemented", 501, "PutObject")
        self.objects[Key] = (Body, f'"{len(self.objects)}-{len(Body)}"')
        return {}

    def head_object(self, *, Bucket: str, Key: str) -> Any:
        if Key not in self.objects:
            raise _failure("404", 404, "HeadObject")
        body, etag = self.objects[Key]
        return {"ContentLength": len(body), "ETag": etag}

    def list_objects_v2(self, **_: Any) -> Any:
        return {"KeyCount": 0, "Contents": []}


@pytest.fixture
def storage() -> tuple[S3Storage, _OldStore]:
    made = S3Storage(
        S3Options.model_validate(
            {
                "endpoint": "http://127.0.0.1:1",
                "access_key_id": "key",
                "secret_access_key": "secret",
                "bucket": "data",
            }
        )
    )
    store = _OldStore()
    made._client = store  # type: ignore[assignment]  # a stand-in that answers the four calls used
    return made, store


def _publish(
    storage: S3Storage,
    tmp_path: Path,
    body: bytes,
    *,
    replace: bool,
    expected: str | None,
) -> None:
    place = storage.place("notes.txt")
    staged = tmp_path / "staged"
    staged.write_bytes(body)
    storage.publish(staged, place, replace=replace, expected_version=expected)


def test_a_new_name_is_claimed_by_asking_first(
    storage: tuple[S3Storage, _OldStore], tmp_path: Path
) -> None:
    made, store = storage

    _publish(made, tmp_path, b"first", replace=False, expected=None)

    assert store.objects["notes.txt"][0] == b"first"
    with pytest.raises(FileExistsError):
        _publish(made, tmp_path, b"second", replace=False, expected=None)


def test_a_changed_version_is_found_by_asking_first(
    storage: tuple[S3Storage, _OldStore], tmp_path: Path
) -> None:
    made, store = storage
    _publish(made, tmp_path, b"first", replace=False, expected=None)
    read_as = store.objects["notes.txt"][1]
    _publish(made, tmp_path, b"meanwhile", replace=True, expected=None)

    with pytest.raises(VersionChanged):
        _publish(made, tmp_path, b"mine", replace=True, expected=read_as)
    assert store.objects["notes.txt"][0] == b"meanwhile"
