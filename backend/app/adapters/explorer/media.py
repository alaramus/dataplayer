"""Verifying a container by its own header, and reading what it states.

The catalog classifies by name, so nothing here trusts a suffix: the media type
returned is the one the bytes prove, and a file whose header does not match the
name it was given is refused before a byte is served (D52).

Everything is a bounded read of a header. There is no decoder: a duration the
container does not state is absent rather than estimated, and which codecs are
inside is left to the browser that tries to play them.

A reader is handed an open handle rather than a path, and reads it only at the
offsets the header names: a recording on a remote storage is asked for a few
blocks, never copied here first (D152).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO, assert_never

from app.adapters.content import AudioMediaType, VideoMediaType
from app.adapters.explorer.formats import format_of
from app.core.translation import N_, say

# A PDF reader looks for the header in the first kilobyte rather than at byte
# zero, because generators put junk in front of it. This does the same.
PDF_HEADER_BYTES = 1024

# ISO base media files hold their index in `moov`, which may sit at the end.
# The boxes are walked by their own sizes, so what is read is one header per
# top-level box; the count is bounded in case a file's sizes form a loop.
MAX_BOXES = 4096

# A `moov` box is the whole index of a recording and can be several megabytes.
# Beyond this it is left unparsed and the recording states no duration.
MAX_MOOV_BYTES = 32 * 1024 * 1024

# A WAV file is a list of chunks, and the two that matter come early.
MAX_RIFF_CHUNKS = 64
MAX_FMT_BYTES = 64

AUDIO_MEDIA_TYPES: dict[str, AudioMediaType] = {
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}
VIDEO_MEDIA_TYPES: dict[str, VideoMediaType] = {
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".ogv": "video/ogg",
    ".webm": "video/webm",
}


class NotPlayable(ValueError):
    """The bytes are not the container the file's name promised."""


@dataclass(frozen=True)
class AudioFacts:
    media_type: AudioMediaType
    duration_seconds: float | None = None
    channels: int | None = None
    sample_rate: int | None = None


@dataclass(frozen=True)
class VideoFacts:
    media_type: VideoMediaType
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class PdfFacts:
    version: str


def audio_facts(name: str, handle: BinaryIO) -> AudioFacts:
    """Verify one sound file and read what its header states. Blocking."""
    media_type = AUDIO_MEDIA_TYPES.get(_suffix(name))
    if media_type is None or format_of(name) != "audio":
        raise NotPlayable(say("This file is not a sound file this source plays"))

    match media_type:
        case "audio/wav":
            return _wav(handle, media_type)
        case "audio/flac":
            return _flac(handle, media_type)
        case "audio/mpeg":
            _verify_mp3(handle)
            return AudioFacts(media_type=media_type)
        case "audio/ogg":
            _verify_magic(handle, b"OggS", N_("This file is not an Ogg file"))
            return AudioFacts(media_type=media_type)
        case "audio/mp4":
            duration, _ = _iso_base_media(handle)
            return AudioFacts(media_type=media_type, duration_seconds=duration)
        case unreachable:
            assert_never(unreachable)


def video_facts(name: str, handle: BinaryIO) -> VideoFacts:
    """Verify one recording and read what its header states. Blocking."""
    media_type = VIDEO_MEDIA_TYPES.get(_suffix(name))
    if media_type is None or format_of(name) != "video":
        raise NotPlayable(say("This file is not a recording this source plays"))

    match media_type:
        case "video/mp4" | "video/quicktime":
            duration, size = _iso_base_media(handle)
            width, height = size if size is not None else (None, None)
            return VideoFacts(
                media_type=media_type,
                duration_seconds=duration,
                width=width,
                height=height,
            )
        case "video/webm":
            _verify_matroska(handle)
            return VideoFacts(media_type=media_type)
        case "video/ogg":
            _verify_magic(handle, b"OggS", N_("This file is not an Ogg file"))
            return VideoFacts(media_type=media_type)
        case unreachable:
            assert_never(unreachable)


def pdf_facts(name: str, handle: BinaryIO) -> PdfFacts:
    """Verify one PDF and read the version it states. Blocking."""
    if format_of(name) != "pdf":
        raise NotPlayable(say("This file is not a PDF"))
    head = handle.read(PDF_HEADER_BYTES)
    position = head.find(b"%PDF-")
    if position < 0:
        raise NotPlayable(say("This file is not a PDF"))
    version = head[position + 5 : position + 8].decode("ascii", errors="replace")
    if len(version) < 3 or not version[0].isdigit() or version[1] != ".":
        raise NotPlayable(say("This PDF does not state a version"))
    return PdfFacts(version=version)


def _suffix(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


def _verify_magic(handle: BinaryIO, magic: bytes, refusal: str) -> None:
    if handle.read(len(magic)) != magic:
        raise NotPlayable(say(refusal))


def _verify_mp3(handle: BinaryIO) -> None:
    """An ID3v2 tag or a frame sync, which is all an MP3 header is."""
    head = handle.read(3)
    if head == b"ID3":
        return
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return
    raise NotPlayable(say("This file is not an MP3"))


def _wav(handle: BinaryIO, media_type: AudioMediaType) -> AudioFacts:
    """RIFF/WAVE, whose `fmt ` and `data` chunks give an exact duration.

    Only chunk headers and the small `fmt ` payload are read: the length of
    `data` is what the duration needs, and `data` is the recording itself.
    """
    header = handle.read(12)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise NotPlayable(say("This file is not a WAV file"))

    channels: int | None = None
    sample_rate: int | None = None
    byte_rate: int | None = None
    duration: float | None = None
    for _ in range(MAX_RIFF_CHUNKS):
        chunk = handle.read(8)
        if len(chunk) < 8:
            break
        kind = chunk[:4]
        length = int.from_bytes(chunk[4:8], "little")
        if kind == b"data":
            if byte_rate:
                duration = length / byte_rate
            break
        if kind == b"fmt ":
            payload = handle.read(min(length, MAX_FMT_BYTES))
            if len(payload) >= 16:
                channels = int.from_bytes(payload[2:4], "little") or None
                sample_rate = int.from_bytes(payload[4:8], "little") or None
                byte_rate = int.from_bytes(payload[8:12], "little") or None
            handle.seek(length - len(payload) + length % 2, 1)
            continue
        # A chunk this reader has no use for: skipped by its own length, plus
        # the pad byte RIFF adds to keep every chunk on an even offset.
        handle.seek(length + length % 2, 1)
    return AudioFacts(
        media_type=media_type,
        duration_seconds=duration,
        channels=channels,
        sample_rate=sample_rate,
    )


def _flac(handle: BinaryIO, media_type: AudioMediaType) -> AudioFacts:
    """`fLaC` and STREAMINFO, which states the exact number of samples."""
    if handle.read(4) != b"fLaC":
        raise NotPlayable(say("This file is not a FLAC file"))
    header = handle.read(4)
    if len(header) < 4:
        raise NotPlayable(say("This FLAC file has no stream information"))
    if header[0] & 0x7F != 0:
        # STREAMINFO is required to be the first metadata block.
        raise NotPlayable(say("This FLAC file has no stream information"))
    block = handle.read(int.from_bytes(header[1:4], "big"))
    if len(block) < 18:
        raise NotPlayable(say("This FLAC file has no stream information"))

    packed = int.from_bytes(block[10:18], "big")
    sample_rate = (packed >> 44) & 0xFFFFF
    channels = ((packed >> 41) & 0x7) + 1
    samples = packed & 0xFFFFFFFFF
    return AudioFacts(
        media_type=media_type,
        duration_seconds=samples / sample_rate if sample_rate and samples else None,
        channels=channels,
        sample_rate=sample_rate or None,
    )


def _iso_base_media(
    handle: BinaryIO,
) -> tuple[float | None, tuple[int, int] | None]:
    """Duration and picture size of an MP4, M4A or MOV.

    The top-level boxes are walked by the sizes they state, so nothing but a
    box header is read until `moov` is found — which in a file that was never
    prepared for streaming is at the very end.
    """
    header = handle.read(8)
    if len(header) < 8 or header[4:8] != b"ftyp":
        raise NotPlayable(say("This file is not an MP4 container"))

    end = handle.seek(0, 2)
    for kind, start, stop in _boxes(handle, 0, end):
        if kind != b"moov":
            continue
        if stop - start > MAX_MOOV_BYTES:
            return None, None
        return _moov(handle, start, stop)
    return None, None


def _moov(
    handle: BinaryIO, start: int, stop: int
) -> tuple[float | None, tuple[int, int] | None]:
    duration: float | None = None
    size: tuple[int, int] | None = None
    for kind, inner_start, inner_stop in _boxes(handle, start, stop):
        if kind == b"mvhd":
            duration = _mvhd(handle, inner_start, inner_stop)
        elif kind == b"trak" and size is None:
            size = _trak(handle, inner_start, inner_stop)
    return duration, size


def _mvhd(handle: BinaryIO, start: int, stop: int) -> float | None:
    handle.seek(start)
    payload = handle.read(min(stop - start, 32))
    if len(payload) < 20:
        return None
    version = payload[0]
    if version == 1:
        if len(payload) < 32:
            return None
        timescale = int.from_bytes(payload[20:24], "big")
        ticks = int.from_bytes(payload[24:32], "big")
    else:
        timescale = int.from_bytes(payload[12:16], "big")
        ticks = int.from_bytes(payload[16:20], "big")
    return ticks / timescale if timescale and ticks else None


def _trak(handle: BinaryIO, start: int, stop: int) -> tuple[int, int] | None:
    """The picture size of one track, from its `tkhd`, or None for a sound one."""
    for kind, inner_start, inner_stop in _boxes(handle, start, stop):
        if kind != b"tkhd":
            continue
        handle.seek(inner_start)
        payload = handle.read(min(inner_stop - inner_start, 96))
        # Where the picture size sits in a `tkhd`: after the times, the ids and
        # the display matrix, which are eight bytes longer in version 1.
        offset = 88 if payload[:1] == b"\x01" else 76
        if len(payload) < offset + 8:
            return None
        width = int.from_bytes(payload[offset : offset + 4], "big") >> 16
        height = int.from_bytes(payload[offset + 4 : offset + 8], "big") >> 16
        return (width, height) if width and height else None
    return None


def _boxes(
    handle: BinaryIO, start: int, stop: int
) -> Iterator[tuple[bytes, int, int]]:
    """Every box between two offsets: its kind and where its payload lies."""
    offset = start
    for _ in range(MAX_BOXES):
        if offset + 8 > stop:
            return
        handle.seek(offset)
        header = handle.read(8)
        if len(header) < 8:
            return
        size = int.from_bytes(header[:4], "big")
        kind = header[4:8]
        payload = offset + 8
        if size == 1:
            extended = handle.read(8)
            if len(extended) < 8:
                return
            size = int.from_bytes(extended, "big")
            payload = offset + 16
        elif size == 0:
            size = stop - offset
        if size < payload - offset:
            return
        yield kind, payload, min(offset + size, stop)
        offset += size


def _verify_matroska(handle: BinaryIO) -> None:
    """The EBML header, read as far as its `DocType`."""
    if handle.read(4) != b"\x1a\x45\xdf\xa3":
        raise NotPlayable(say("This file is not a WebM file"))
    length = _ebml_length(handle)
    if length is None:
        raise NotPlayable(say("This file is not a WebM file"))
    header = handle.read(min(length, 4096))
    marker = header.find(b"\x42\x82")
    if marker < 0:
        raise NotPlayable(say("This WebM file states no document type"))
    # The DocType element's own length is one byte for any name this short.
    size = header[marker + 2] & 0x7F
    doc_type = header[marker + 3 : marker + 3 + size].rstrip(b"\0")
    if doc_type not in (b"webm", b"matroska"):
        raise NotPlayable(say("This file is not a WebM file"))


def _ebml_length(handle: BinaryIO) -> int | None:
    """One EBML variable-length integer, as the header's size is written."""
    first = handle.read(1)
    if not first:
        return None
    marker = first[0]
    if marker == 0:
        return None
    width = 8 - marker.bit_length() + 1
    value = marker & (0xFF >> width)
    rest = handle.read(width - 1)
    if len(rest) < width - 1:
        return None
    for byte in rest:
        value = (value << 8) | byte
    return value
