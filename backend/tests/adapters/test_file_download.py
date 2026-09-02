import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.adapters.actions import ActionDownload, ActionRefused, ProducesDownload
from app.adapters.file.actions import FileActions
from app.adapters.file.session import FileSession


async def _download(root: Path, node_ids: list[str]) -> ActionDownload:
    action = FileActions(FileSession(root)).action("download")
    assert isinstance(action, ProducesDownload)
    return await action.download(node_ids, {})


async def test_one_file_downloads_as_its_unchanged_original(tmp_path: Path) -> None:
    source = b"\x00original\xffbytes"
    (tmp_path / "opaque.bin").write_bytes(source)

    prepared = await _download(tmp_path, ["opaque.bin"])

    assert prepared.metadata.filename == "opaque.bin"
    assert prepared.metadata.media_type == "application/octet-stream"
    assert prepared.metadata.size_bytes == len(source)
    assert b"".join([chunk async for chunk in prepared.body]) == source


async def test_one_folder_downloads_as_an_archive_with_its_name(
    tmp_path: Path,
) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_bytes(b"id,name\n1,one\n")
    (tmp_path / "reports" / "empty").mkdir()

    prepared = await _download(tmp_path, ["reports"])
    body = b"".join([chunk async for chunk in prepared.body])

    assert prepared.metadata.filename == "reports.zip"
    assert prepared.metadata.media_type == "application/zip"
    with ZipFile(io.BytesIO(body)) as archive:
        assert archive.namelist() == [
            "reports/",
            "reports/empty/",
            "reports/q3.csv",
        ]
        assert archive.read("reports/q3.csv") == b"id,name\n1,one\n"


async def test_several_nodes_download_as_one_archive(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("q3")

    prepared = await _download(tmp_path, ["notes.txt", "reports"])
    body = b"".join([chunk async for chunk in prepared.body])

    assert prepared.metadata.filename == "download.zip"
    with ZipFile(io.BytesIO(body)) as archive:
        assert archive.read("notes.txt") == b"notes"
        assert archive.read("reports/q3.csv") == b"q3"


async def test_an_archive_stops_at_its_source_byte_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.adapters.file import download as file_download

    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "large.bin").write_bytes(b"1234")
    monkeypatch.setattr(file_download, "MAX_ARCHIVE_BYTES", 3)

    with pytest.raises(ActionRefused) as caught:
        await _download(tmp_path, ["folder"])

    assert caught.value.reason == "too_large"
