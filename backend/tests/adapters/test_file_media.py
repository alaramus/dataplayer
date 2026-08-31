"""Containers verified by their own headers, and the bytes read by range."""

import wave
from pathlib import Path

import pytest

from app.adapters.content import AudioContent, PdfContent, VideoContent
from app.adapters.file.content import FileContent
from app.adapters.file.media import NotPlayable, audio_facts, pdf_facts, video_facts
from app.adapters.file.session import FileSession
from tests.utils.media import (
    flac_bytes,
    matroska_bytes,
    mp3_bytes,
    mp4_bytes,
    ogg_bytes,
    pdf_bytes,
    wav_bytes,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    wav_bytes(tmp_path / "tone.wav", seconds=2, rate=8000, channels=1)
    (tmp_path / "song.flac").write_bytes(flac_bytes(rate=44100, channels=2, samples=88200))
    (tmp_path / "voice.mp3").write_bytes(mp3_bytes())
    (tmp_path / "stream.ogg").write_bytes(ogg_bytes())
    (tmp_path / "clip.mp4").write_bytes(mp4_bytes(timescale=1000, duration=5500))
    (tmp_path / "clip.webm").write_bytes(matroska_bytes())
    (tmp_path / "report.pdf").write_bytes(pdf_bytes())
    # Each of these is named as something it is not.
    (tmp_path / "fake.mp3").write_bytes(b"not audio at all")
    (tmp_path / "fake.webm").write_bytes(b"not a matroska file")
    (tmp_path / "fake.pdf").write_bytes(b"%PS-Adobe-3.0\n")
    return tmp_path


@pytest.fixture
def content(root: Path) -> FileContent:
    return FileContent(FileSession(root))


def test_a_wav_states_its_channels_rate_and_exact_length(root: Path) -> None:
    facts = audio_facts(root / "tone.wav")

    assert facts.media_type == "audio/wav"
    assert facts.channels == 1
    assert facts.sample_rate == 8000
    assert facts.duration_seconds == pytest.approx(2.0)


def test_a_flac_states_an_exact_length_from_its_sample_count(root: Path) -> None:
    facts = audio_facts(root / "song.flac")

    assert facts.media_type == "audio/flac"
    assert facts.channels == 2
    assert facts.sample_rate == 44100
    assert facts.duration_seconds == pytest.approx(2.0)


def test_an_mp3_is_verified_and_states_no_length(root: Path) -> None:
    """A duration would mean scanning the frames, so it is absent, not guessed."""
    facts = audio_facts(root / "voice.mp3")

    assert facts.media_type == "audio/mpeg"
    assert facts.duration_seconds is None


def test_an_ogg_file_is_verified_by_its_magic(root: Path) -> None:
    assert audio_facts(root / "stream.ogg").media_type == "audio/ogg"


def test_an_mp4_states_its_length_and_picture_size(root: Path) -> None:
    facts = video_facts(root / "clip.mp4")

    assert facts.media_type == "video/mp4"
    assert facts.duration_seconds == pytest.approx(5.5)
    assert (facts.width, facts.height) == (1280, 720)


def test_an_mp4_whose_index_sits_at_the_end_is_still_read(tmp_path: Path) -> None:
    """A file that was never prepared for streaming keeps `moov` last."""
    (tmp_path / "late.mp4").write_bytes(
        mp4_bytes(timescale=600, duration=1200, moov_last=True)
    )

    facts = video_facts(tmp_path / "late.mp4")

    assert facts.duration_seconds == pytest.approx(2.0)
    assert (facts.width, facts.height) == (1280, 720)


def test_a_webm_must_say_it_is_one(root: Path) -> None:
    assert video_facts(root / "clip.webm").media_type == "video/webm"

    with pytest.raises(NotPlayable, match="not a WebM file"):
        video_facts(root / "fake.webm")


def test_a_pdf_states_the_version_in_its_header(root: Path) -> None:
    assert pdf_facts(root / "report.pdf").version == "1.7"


def test_bytes_that_are_not_the_named_container_are_refused(root: Path) -> None:
    with pytest.raises(NotPlayable, match="not an MP3"):
        audio_facts(root / "fake.mp3")
    with pytest.raises(NotPlayable, match="not a PDF"):
        pdf_facts(root / "fake.pdf")


def test_a_recording_is_not_offered_as_a_sound_file(root: Path) -> None:
    """The two readers answer for their own representation and no other."""
    with pytest.raises(NotPlayable):
        audio_facts(root / "clip.mp4")
    with pytest.raises(NotPlayable):
        video_facts(root / "voice.mp3")


async def test_content_carries_the_verified_facts(content: FileContent) -> None:
    from app.adapters.content import ContentRequest

    sound = await content.read_content(
        ContentRequest(node_id="tone.wav", representation="audio")
    )
    assert isinstance(sound, AudioContent)
    assert sound.media_type == "audio/wav"
    assert sound.sample_rate == 8000
    assert sound.stream_url is None  # minted by the route, never by the source

    clip = await content.read_content(
        ContentRequest(node_id="clip.mp4", representation="video")
    )
    assert isinstance(clip, VideoContent)
    assert (clip.width, clip.height) == (1280, 720)

    document = await content.read_content(
        ContentRequest(node_id="report.pdf", representation="pdf")
    )
    assert isinstance(document, PdfContent)
    assert document.version == "1.7"
    assert document.media_type == "application/pdf"


async def test_a_stream_states_the_size_and_reads_only_the_range(
    content: FileContent, root: Path
) -> None:
    from app.adapters.content import ContentRequest

    stream = await content.open_content_stream(
        ContentRequest(node_id="tone.wav", representation="audio")
    )

    assert stream.size_bytes == (root / "tone.wav").stat().st_size
    assert stream.media_type == "audio/wav"
    assert stream.filename == "tone.wav"

    whole = (root / "tone.wav").read_bytes()
    part = b"".join([chunk async for chunk in stream.read(10, 19)])
    assert part == whole[10:20]


async def test_a_stream_of_a_representation_the_file_does_not_offer_is_refused(
    content: FileContent,
) -> None:
    from app.adapters.content import ContentRequest

    with pytest.raises(ValueError, match="does not offer"):
        await content.open_content_stream(
            ContentRequest(node_id="tone.wav", representation="video")
        )


async def test_a_text_file_is_not_streamed(content: FileContent) -> None:
    from app.adapters.content import ContentRequest

    with pytest.raises(ValueError):
        await content.open_content_stream(
            ContentRequest(node_id="report.pdf", representation="text")
        )


def test_wave_fixture_is_a_real_wav(root: Path) -> None:
    """The fixtures are real containers; a test on invented bytes proves nothing."""
    with wave.open(str(root / "tone.wav"), "rb") as handle:
        assert handle.getframerate() == 8000
