"""Real container headers, built by hand, for the media tests of D52.

Real ones: a verifier tested against bytes that only look like a header proves
nothing about a file a browser would play. Each builder writes the structure
the format actually defines, and nothing beyond what the reader looks at.
"""

import struct
import wave
from pathlib import Path


def wav_bytes(path: Path, *, seconds: int, rate: int, channels: int) -> None:
    """A real WAV file of silence, written by the standard library."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\0" * (seconds * rate * channels * 2))


def flac_bytes(*, rate: int, channels: int, samples: int) -> bytes:
    """`fLaC` and a STREAMINFO block stating rate, channels and sample count."""
    packed = (
        (rate << 44)
        | ((channels - 1) << 41)
        | ((16 - 1) << 36)
        | (samples & 0xFFFFFFFFF)
    )
    stream_info = (
        struct.pack(">HH", 4096, 4096)  # minimum and maximum block size
        + (0).to_bytes(3, "big")  # minimum frame size
        + (0).to_bytes(3, "big")  # maximum frame size
        + packed.to_bytes(8, "big")
        + b"\0" * 16  # the MD5 of the unencoded audio
    )
    header = bytes([0x80]) + len(stream_info).to_bytes(3, "big")
    return b"fLaC" + header + stream_info


def mp3_bytes() -> bytes:
    """An ID3v2 tag followed by one frame sync, as a tagged MP3 begins."""
    return b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\0" * 64


def ogg_bytes() -> bytes:
    return b"OggS" + b"\0" * 64


def matroska_bytes(doc_type: bytes = b"webm") -> bytes:
    """An EBML header carrying a DocType, which is what is verified."""
    body = (
        b"\x42\x86\x81\x01"  # EBMLVersion
        b"\x42\xf7\x81\x01"  # EBMLReadVersion
        + b"\x42\x82"
        + bytes([0x80 | len(doc_type)])
        + doc_type
    )
    return b"\x1a\x45\xdf\xa3" + bytes([0x80 | len(body)]) + body + b"\0" * 32


def mp4_bytes(
    *,
    timescale: int,
    duration: int,
    width: int = 1280,
    height: int = 720,
    moov_last: bool = False,
) -> bytes:
    """An ISO base media file with the two boxes the reader looks at.

    `moov_last` puts the index at the end, as a file that was never prepared
    for streaming has it, with a payload box in front of it to walk past.
    """
    header = _box(b"ftyp", b"isom" + (512).to_bytes(4, "big") + b"isomiso2mp41")
    movie = _box(b"moov", _mvhd(timescale, duration) + _trak(width, height))
    payload = _box(b"mdat", b"\0" * 512)
    return header + (payload + movie if moov_last else movie + payload)


def _box(kind: bytes, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + kind + payload


def _mvhd(timescale: int, duration: int) -> bytes:
    payload = (
        b"\0\0\0\0"  # version 0 and flags
        + (0).to_bytes(4, "big")  # creation time
        + (0).to_bytes(4, "big")  # modification time
        + timescale.to_bytes(4, "big")
        + duration.to_bytes(4, "big")
        + b"\0" * 80  # rate, volume, matrix and the next track id
    )
    return _box(b"mvhd", payload)


def _trak(width: int, height: int) -> bytes:
    payload = (
        b"\0\0\0\0"  # version 0 and flags
        + (0).to_bytes(4, "big")  # creation time
        + (0).to_bytes(4, "big")  # modification time
        + (1).to_bytes(4, "big")  # track id
        + (0).to_bytes(4, "big")  # reserved
        + (0).to_bytes(4, "big")  # duration
        + b"\0" * 8  # reserved
        + b"\0\0"  # layer
        + b"\0\0"  # alternate group
        + b"\0\0"  # volume
        + b"\0\0"  # reserved
        + b"\0" * 36  # display matrix
        + (width << 16).to_bytes(4, "big")
        + (height << 16).to_bytes(4, "big")
    )
    return _box(b"trak", _box(b"tkhd", payload))


def pdf_bytes(version: str = "1.7") -> bytes:
    """The smallest document a reader accepts: one empty page."""
    body = (
        f"%PDF-{version}\n"
        "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
        "trailer<</Root 1 0 R/Size 4>>\n"
        "%%EOF\n"
    )
    return body.encode("ascii")


def padded(path: Path, head: bytes, size: int, tail: bytes = b"") -> None:
    """A file of `size` bytes: a real beginning, zeros, and a real ending.

    The middle is never written, so a recording of hundreds of megabytes costs
    a test no more than its two ends.
    """
    with path.open("wb") as out:
        out.write(head)
        out.seek(size - len(tail))
        out.write(tail)
        out.truncate(size)


def large_mp4(path: Path, *, payload_bytes: int, timescale: int, duration: int) -> None:
    """An MP4 whose index sits behind a payload this large, as it does in a
    recording that was never prepared for streaming."""
    header = _box(b"ftyp", b"isom" + (512).to_bytes(4, "big") + b"isomiso2mp41")
    movie = _box(b"moov", _mvhd(timescale, duration) + _trak(1280, 720))
    payload = (payload_bytes + 8).to_bytes(4, "big") + b"mdat"
    padded(path, header + payload, len(header) + 8 + payload_bytes + len(movie), movie)


def large_wav(path: Path, *, data_bytes: int, rate: int, channels: int) -> None:
    """A WAV header stating a `data` chunk this large, followed by its silence."""
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 2, channels * 2, 16)
    head = (
        b"RIFF"
        + (36 + data_bytes).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + len(fmt).to_bytes(4, "little")
        + fmt
        + b"data"
        + data_bytes.to_bytes(4, "little")
    )
    padded(path, head, len(head) + data_bytes)
