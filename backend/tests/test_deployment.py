"""The files that start the backend start one process (D124).

Development runs `fastapi dev`, a single reloading process, so a second worker
in the image breaks nothing anybody working on the code can see. This is where
it is caught instead.
"""

import json
import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def _image_command() -> list[str]:
    text = (REPOSITORY / "backend" / "Dockerfile").read_text(encoding="utf-8")
    commands = re.findall(r"^CMD\s+(.+)$", text, flags=re.MULTILINE)
    assert len(commands) == 1, "the image should have exactly one CMD"
    command = json.loads(commands[0])
    assert isinstance(command, list)
    return [str(part) for part in command]


def test_the_image_names_exactly_one_worker() -> None:
    """Named, not defaulted: without the flag uvicorn reads `WEB_CONCURRENCY`."""
    command = _image_command()

    assert command[:2] == ["fastapi", "run"]
    assert not [part for part in command if part.startswith("--workers=")]
    assert command.count("--workers") == 1
    assert command[command.index("--workers") + 1] == "1"


def test_no_compose_file_asks_for_a_worker_count() -> None:
    for name in ("compose.yml", "compose.override.yml"):
        text = (REPOSITORY / name).read_text(encoding="utf-8")

        assert "--workers" not in text, name
        assert "WEB_CONCURRENCY" not in text, name
