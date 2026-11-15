"""An attachment kept in its owner's folder (D371).

Under `Mail/<address>/` of the person's storage: a folder the server names,
never the client (D8), and a write that counts against the person's limit
(D324).
"""

import re
from pathlib import Path, PurePosixPath

from app.adapters.actions import StorageFull
from app.adapters.explorer.storage import is_plain_name
from app.users.storage import used_bytes

FOLDER = "Mail"
_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_MAX_NAME = 150


def safe_name(name: str, fallback: str = "attachment") -> str:
    """A name both platforms take as one plain file name."""
    cleaned = _UNSAFE.sub("_", name).strip().rstrip(". ")
    if len(cleaned) > _MAX_NAME:
        path = PurePosixPath(cleaned)
        suffix = path.suffix[:20]
        cleaned = path.stem[: _MAX_NAME - len(suffix)] + suffix
    return cleaned if cleaned and is_plain_name(cleaned) else fallback


def keep_attachment(
    *, home: Path, address: str, filename: str, body: bytes, limit_bytes: int | None
) -> str:
    """Write the bytes beside nothing they would replace; the path in the home.

    Blocking work: the caller runs it in a thread.
    """
    directory = home / FOLDER / safe_name(address, "mailbox")
    for one in (home, home / FOLDER, directory):
        if one.is_symlink():
            raise ValueError("The mail folder is not safe")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.resolve().relative_to(home.resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError("The mail folder is not safe") from None

    if limit_bytes is not None:
        after = used_bytes(home) + len(body)
        if after > limit_bytes:
            raise StorageFull(after, limit_bytes)

    name = safe_name(filename)
    stem, suffix = PurePosixPath(name).stem, PurePosixPath(name).suffix
    destination = directory / name
    number = 2
    while destination.exists():
        destination = directory / f"{stem} ({number}){suffix}"
        number += 1
    temporary = destination.with_name(destination.name + ".part")
    try:
        temporary.write_bytes(body)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination.relative_to(home).as_posix()
