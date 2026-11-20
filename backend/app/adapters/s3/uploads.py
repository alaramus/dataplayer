"""An object written in pieces: one PUT when it is small, a multipart upload
when it is not (D380).

A part is held in memory until it is sent, so a transfer of gigabytes holds
one part on this machine (D168). An upload that is not completed is aborted:
parts left behind are billed and invisible.
"""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from types_boto3_s3.client import S3Client

T = TypeVar("T")

# S3 refuses a part under 5 MB except the last, and an upload of more than
# 10,000 parts; a part grows by 8 MB every thousand, so an object may reach
# far past what anything here sends.
PART_BYTES = 8 * 1024 * 1024
PARTS_PER_STEP = 1000

Asked = Callable[[Callable[["S3Client"], T]], T]


class Upload:
    """Bytes on their way to one key, sent as they arrive."""

    def __init__(self, asked: Asked[Any], bucket: str, key: str) -> None:
        self._asked = asked
        self._bucket = bucket
        self._key = key
        self._buffer = bytearray()
        self._upload_id: str | None = None
        self._parts: list[dict[str, Any]] = []

    def write(self, data: bytes) -> None:
        self._buffer += data
        while len(self._buffer) >= self._part_bytes():
            size = self._part_bytes()
            self._send(bytes(self._buffer[:size]))
            del self._buffer[:size]

    def finish(self, conditions: Mapping[str, Any]) -> None:
        """Put it in place, under the conditions given: `If-None-Match` to
        claim the name, `If-Match` to replace one version."""
        if self._upload_id is None:
            body = bytes(self._buffer)
            self._asked(
                lambda client: client.put_object(
                    Bucket=self._bucket, Key=self._key, Body=body, **conditions
                )
            )
            return
        if self._buffer:
            self._send(bytes(self._buffer))
            self._buffer.clear()
        upload_id, parts = self._upload_id, list(self._parts)
        self._asked(
            lambda client: client.complete_multipart_upload(
                Bucket=self._bucket,
                Key=self._key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},  # type: ignore[typeddict-item]  # the stubs want CompletedPartTypeDef, which this list is
                **conditions,
            )
        )
        self._upload_id = None

    def abort(self) -> None:
        upload_id = self._upload_id
        self._upload_id = None
        self._buffer.clear()
        if upload_id is None:
            return
        self._asked(
            lambda client: client.abort_multipart_upload(
                Bucket=self._bucket, Key=self._key, UploadId=upload_id
            )
        )

    def _part_bytes(self) -> int:
        return PART_BYTES * (1 + len(self._parts) // PARTS_PER_STEP)

    def _send(self, chunk: bytes) -> None:
        if self._upload_id is None:
            started = self._asked(
                lambda client: client.create_multipart_upload(
                    Bucket=self._bucket, Key=self._key
                )
            )
            self._upload_id = str(started["UploadId"])
        upload_id = self._upload_id
        number = len(self._parts) + 1
        sent = self._asked(
            lambda client: client.upload_part(
                Bucket=self._bucket,
                Key=self._key,
                UploadId=upload_id,
                PartNumber=number,
                Body=chunk,
            )
        )
        self._parts.append({"ETag": sent["ETag"], "PartNumber": number})
