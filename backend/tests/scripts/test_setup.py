"""The first-run setup fills placeholders, never chosen values."""

import base64
import builtins
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_PATH = REPO_ROOT / "scripts" / "setup.py"


def load_setup() -> object:
    spec = importlib.util.spec_from_file_location("dataplayer_setup", SETUP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["dataplayer_setup"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def setup() -> object:
    return load_setup()


@pytest.fixture()
def env_copy(tmp_path: Path) -> Path:
    target = tmp_path / ".env"
    shutil.copy(REPO_ROOT / ".env.example", target)
    return target


def test_generated_key_is_32_urlsafe_bytes(setup: object) -> None:
    raw = base64.urlsafe_b64decode(setup.generate_key())  # type: ignore[attr-defined]
    assert len(raw) == 32


def test_generated_password_needs_no_url_encoding(setup: object) -> None:
    password = setup.generate_password()  # type: ignore[attr-defined]
    assert len(password) >= 8
    assert all(char.isascii() and char.isalnum() or char in "-_" for char in password)


def test_placeholder_is_filled_but_a_choice_is_kept(
    setup: object, env_copy: Path
) -> None:
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    report = setup.Report()  # type: ignore[attr-defined]
    choices = setup.Choices("prod", "minimal", False)  # type: ignore[attr-defined]
    setup.configure(env, choices, report)  # type: ignore[attr-defined]
    assert "SECRET_KEY" in report.generated
    first = env.get("SECRET_KEY")
    assert first not in (None, "", "changethis")
    second_report = setup.Report()  # type: ignore[attr-defined]
    setup.configure(env, choices, second_report)  # type: ignore[attr-defined]
    assert env.get("SECRET_KEY") == first
    assert "SECRET_KEY" not in second_report.generated


def test_minimal_prod_runs_on_memory_without_meaning(
    setup: object, env_copy: Path
) -> None:
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    report = setup.Report()  # type: ignore[attr-defined]
    choices = setup.Choices("prod", "minimal", False)  # type: ignore[attr-defined]
    # A stale model address from an earlier preset does not survive minimal.
    env.set("EMBEDDINGS_URL", "http://embedder:80")
    setup.configure(env, choices, report)  # type: ignore[attr-defined]
    assert env.get("DATA_CACHE_BACKEND") == "memory"
    assert env.get("EMBEDDINGS_URL") == ""
    assert "EMBEDDINGS_URL (cleared)" in report.changed
    assert env.get("COMPOSE_FILE") == "compose.yml,compose.prod.yml"
    assert env.get("COMPOSE_PROFILES") == ""
    assert env.get("FASTAPI_ENV") is None
    assert env.get("DATA_CACHE_DEPLOYMENT") == "production"
    assert env.get("FRONTEND_HOST") == "http://localhost:8000"
    assert env.get("SERVICES_ENABLED") == "false"


def test_meaning_url_is_synced_both_ways(setup: object, env_copy: Path) -> None:
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    full = setup.Choices("prod", "full", False)  # type: ignore[attr-defined]
    setup.configure(env, full, setup.Report())  # type: ignore[attr-defined]
    assert env.get("EMBEDDINGS_URL") == "http://embedder:80"
    assert env.get("DATA_CACHE_BACKEND") == "redis"
    assert env.get("COMPOSE_PROFILES") == "cache,meaning"

    minimal = setup.Choices("prod", "minimal", False)  # type: ignore[attr-defined]
    report = setup.Report()  # type: ignore[attr-defined]
    setup.configure(env, minimal, report)  # type: ignore[attr-defined]
    assert env.get("EMBEDDINGS_URL") == ""
    assert "EMBEDDINGS_URL (cleared)" in report.changed

    custom = setup.Choices("prod", "full", False)  # type: ignore[attr-defined]
    env.set("EMBEDDINGS_URL", "http://gpu-box:80")
    setup.configure(env, custom, setup.Report())  # type: ignore[attr-defined]
    assert env.get("EMBEDDINGS_URL") == "http://gpu-box:80"


def test_dev_keeps_a_custom_frontend_host(setup: object, env_copy: Path) -> None:
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    env.set("FRONTEND_HOST", "http://192.168.1.10:5173")
    choices = setup.Choices("dev", "full", False)  # type: ignore[attr-defined]
    setup.configure(env, choices, setup.Report())  # type: ignore[attr-defined]
    assert env.get("FRONTEND_HOST") == "http://192.168.1.10:5173"
    assert env.get("FASTAPI_ENV") == "development"


def test_dev_resets_a_stale_prod_frontend_host(
    setup: object, env_copy: Path
) -> None:
    # The API accepts calls from FRONTEND_HOST alone, so a prod address left
    # by an earlier run would lock the Vite interface out with a CORS error.
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    env.set("COMPOSE_FILE", "compose.yml,compose.prod.yml")
    env.set("FRONTEND_HOST", "http://localhost:8000")
    env.set("DATA_CACHE_DEPLOYMENT", "production")
    choices = setup.Choices("dev", "minimal", False)  # type: ignore[attr-defined]
    report = setup.Report()  # type: ignore[attr-defined]
    setup.configure(env, choices, report)  # type: ignore[attr-defined]
    assert env.get("FRONTEND_HOST") == "http://localhost:5173"
    assert "FRONTEND_HOST" in report.changed
    assert env.get("DATA_CACHE_DEPLOYMENT") == "development"


def test_prod_resets_a_dev_frontend_host(setup: object, env_copy: Path) -> None:
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    env.set("FRONTEND_HOST", "http://192.168.1.10:5173")
    choices = setup.Choices("prod", "minimal", False)  # type: ignore[attr-defined]
    setup.configure(env, choices, setup.Report())  # type: ignore[attr-defined]
    assert env.get("FRONTEND_HOST") == "http://localhost:8000"


def test_set_reuses_a_commented_entry(setup: object, env_copy: Path) -> None:
    # A prod run comments FASTAPI_ENV out; the next dev run must flip that
    # line back, not append a duplicate at the end of the file.
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    assert env.comment_out("FASTAPI_ENV")  # type: ignore[attr-defined]
    env.set("FASTAPI_ENV", "development")  # type: ignore[attr-defined]
    assert env.get("FASTAPI_ENV") == "development"
    assert env.lines.count("FASTAPI_ENV=development") == 1


def test_compose_command_follows_env(setup: object) -> None:
    prod = setup.Choices("prod", "minimal", False)  # type: ignore[attr-defined]
    assert setup.compose_command(prod) == [  # type: ignore[attr-defined]
        "docker",
        "compose",
        "up",
        "-d",
        "--build",
    ]
    dev = setup.Choices("dev", "minimal", False)  # type: ignore[attr-defined]
    assert setup.compose_command(dev)[-3:] == [  # type: ignore[attr-defined]
        "backend",
        "metrics",
        "search-keeper",
    ]
    full_dev = setup.Choices("dev", "full", False)  # type: ignore[attr-defined]
    assert setup.compose_command(full_dev)[-1] == "embedder"  # type: ignore[attr-defined]


def test_current_mode_and_preset(setup: object, env_copy: Path) -> None:
    env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
    env.set("COMPOSE_FILE", "compose.yml,compose.prod.yml")
    env.set("COMPOSE_PROFILES", "cache,meaning")
    assert setup.current_mode(env) == "prod"  # type: ignore[attr-defined]
    assert setup.current_preset(env) == "full"  # type: ignore[attr-defined]
    env.set("COMPOSE_PROFILES", "")
    assert setup.current_preset(env) == "minimal"  # type: ignore[attr-defined]


def test_choice_is_numbers_only(
    setup: object, capsys: pytest.CaptureFixture[str]
) -> None:
    real_input = builtins.input
    options = ("minimal", "standard", "full")
    try:
        builtins.input = lambda prompt="": "2"
        ask = setup.ask_choice  # type: ignore[attr-defined]
        assert ask("preset", options, "minimal") == "standard"
        answers = iter(["standart", "3"])
        builtins.input = lambda prompt="": next(answers)
        assert ask("preset", options, "minimal") == "full"
        assert "enter a number" in capsys.readouterr().out
        builtins.input = lambda prompt="": ""
        assert ask("preset", options, "full") == "full"
    finally:
        builtins.input = real_input


def test_wizard_walks_through_every_choice(setup: object, env_copy: Path) -> None:
    real_input = builtins.input
    answers = iter(["1", "2", "owner@example.com", "1", "", "n", "y"])
    builtins.input = lambda prompt="": next(answers)
    try:
        env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
        result = setup.run_wizard(env)  # type: ignore[attr-defined]
    finally:
        builtins.input = real_input
    assert result is not None
    assert (result.mode, result.preset, result.services) == ("prod", "standard", False)
    assert result.email == "owner@example.com"
    # The wizard only answers; configure() writes.
    setup.configure(env, result, setup.Report())  # type: ignore[attr-defined]
    assert env.get("FIRST_SUPERUSER") == "owner@example.com"


def test_wizard_abort_writes_nothing(setup: object, env_copy: Path) -> None:
    real_input = builtins.input
    answers = iter(["1", "", "", "1", "", "n", "n"])
    builtins.input = lambda prompt="": next(answers)
    try:
        env = setup.EnvFile.load(env_copy)  # type: ignore[attr-defined]
        result = setup.run_wizard(env)  # type: ignore[attr-defined]
    finally:
        builtins.input = real_input
    assert result is None


def test_container_run_writes_but_never_starts(
    setup: object,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / ".env"
    shutil.copy(REPO_ROOT / ".env.example", env_path)
    monkeypatch.setenv("SETUP_CONTAINER", "1")

    def fail_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("must not start anything inside the container")

    monkeypatch.setattr(setup.subprocess, "run", fail_run)  # type: ignore[attr-defined]
    code = setup.main(  # type: ignore[attr-defined]
        ["--preset", "minimal", "--mode", "prod", "--yes"],
        env_path=env_path,
        frontend_env_path=tmp_path / "frontend.env",
    )
    assert code == 0
    assert "docker compose up -d --build" in capsys.readouterr().out


def test_decline_stops_the_chain(
    setup: object,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / ".env"
    shutil.copy(REPO_ROOT / ".env.example", env_path)
    before = env_path.read_bytes()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "n")
    code = setup.main(  # type: ignore[attr-defined]
        ["--preset", "minimal", "--mode", "prod"],
        env_path=env_path,
        frontend_env_path=tmp_path / "frontend.env",
    )
    assert code == 1
    assert env_path.read_bytes() == before
    assert "nothing was written" in capsys.readouterr().out


def test_main_writes_but_never_overwrites(
    setup: object, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / ".env"
    shutil.copy(REPO_ROOT / ".env.example", env_path)
    frontend_path = tmp_path / "frontend.env"
    main = setup.main  # type: ignore[attr-defined]
    code = main(
        ["--preset", "minimal", "--mode", "prod", "--no-run"],
        env_path=env_path,
        frontend_env_path=frontend_path,
    )
    assert code == 0
    first = setup.EnvFile.load(env_path)  # type: ignore[attr-defined]
    assert first.get("SECRET_KEY") != "changethis"
    code = main(
        ["--preset", "full", "--mode", "prod", "--no-run"],
        env_path=env_path,
        frontend_env_path=frontend_path,
    )
    assert code == 0
    second = setup.EnvFile.load(env_path)  # type: ignore[attr-defined]
    assert second.get("SECRET_KEY") == first.get("SECRET_KEY")
    assert second.get("DATA_CACHE_BACKEND") == "redis"
    assert second.get("EMBEDDINGS_URL") == "http://embedder:80"
    assert (tmp_path / ".env.bak").exists()
    assert "Setup summary" in capsys.readouterr().out
