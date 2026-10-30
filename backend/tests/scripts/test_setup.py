"""The first-run setup fills placeholders, never chosen values."""

import base64
import importlib.util
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_PATH = REPO_ROOT / "scripts" / "setup.py"
EXAMPLE = REPO_ROOT / ".env.example"


@pytest.fixture(scope="module")
def setup() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("dataplayer_setup", SETUP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses look their module up in sys.modules while the class is made.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    del sys.modules[spec.name]


@pytest.fixture()
def example(setup: ModuleType) -> object:
    return setup.EnvFile.load(EXAMPLE)


def answer(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    given = iter(answers)

    def typed(prompt: str = "") -> str:
        sys.stdout.write(prompt + "\n")  # what a terminal shows, for the output to be read
        return next(given)

    monkeypatch.setattr("builtins.input", typed)


def run(setup: ModuleType, tmp_path: Path, *argv: str) -> int:
    code: int = setup.main(
        list(argv),
        env_path=tmp_path / ".env",
        frontend_env_path=tmp_path / "frontend.env",
    )
    return code


def test_a_generated_key_is_32_urlsafe_bytes(setup: ModuleType) -> None:
    assert len(base64.urlsafe_b64decode(setup.generate_key())) == 32


def test_a_generated_password_needs_no_url_encoding(setup: ModuleType) -> None:
    password = setup.generate_password()
    assert len(password) >= 24
    assert all(char.isascii() and (char.isalnum() or char in "-_") for char in password)


def test_every_placeholder_is_filled_and_then_kept(
    setup: ModuleType, example: object
) -> None:
    choices = setup.Choices("prod", "minimal", False)
    setup.configure(example, choices)
    first = {name: example.get(name) for name in setup.SECRETS}  # type: ignore[attr-defined]
    assert setup.PLACEHOLDER not in first.values()
    setup.configure(example, setup.Choices("dev", "full", False))
    assert {name: example.get(name) for name in setup.SECRETS} == first  # type: ignore[attr-defined]


def test_minimal_prod_runs_on_memory_without_meaning(
    setup: ModuleType, example: object
) -> None:
    example.set("EMBEDDINGS_URL", "http://embedder:80")  # type: ignore[attr-defined]
    setup.configure(example, setup.Choices("prod", "minimal", False))
    get = example.get  # type: ignore[attr-defined]
    assert get("COMPOSE_FILE") == "compose.yml,compose.prod.yml"
    assert get("COMPOSE_PROFILES") == ""
    assert get("DATA_CACHE_BACKEND") == "memory"
    assert get("EMBEDDINGS_URL") == ""
    assert get("FASTAPI_ENV") is None
    assert get("DATA_CACHE_DEPLOYMENT") == "production"
    assert get("FRONTEND_HOST") == "http://localhost:8000"
    assert get("SERVICES_ENABLED") == "false"


def test_full_points_search_at_the_model_and_keeps_another(
    setup: ModuleType, example: object
) -> None:
    setup.configure(example, setup.Choices("prod", "full", False))
    assert example.get("COMPOSE_PROFILES") == "cache,meaning"  # type: ignore[attr-defined]
    assert example.get("DATA_CACHE_BACKEND") == "redis"  # type: ignore[attr-defined]
    assert example.get("EMBEDDINGS_URL") == "http://embedder:80"  # type: ignore[attr-defined]
    example.set("EMBEDDINGS_URL", "http://gpu-box:80")  # type: ignore[attr-defined]
    setup.configure(example, setup.Choices("prod", "full", False))
    assert example.get("EMBEDDINGS_URL") == "http://gpu-box:80"  # type: ignore[attr-defined]


def test_the_api_origin_follows_the_mode(setup: ModuleType, example: object) -> None:
    # The API accepts calls from FRONTEND_HOST alone: a prod address left in
    # development locks the Vite interface out.
    setup.configure(
        example,
        setup.Choices("prod", "minimal", False, host="https://data.example.com"),
    )
    setup.configure(example, setup.Choices("dev", "minimal", False))
    assert example.get("FRONTEND_HOST") == "http://localhost:5173"  # type: ignore[attr-defined]
    assert example.get("FASTAPI_ENV") == "development"  # type: ignore[attr-defined]
    assert example.get("DATA_CACHE_DEPLOYMENT") == "development"  # type: ignore[attr-defined]
    example.set("FRONTEND_HOST", "http://192.168.1.10:5173")  # type: ignore[attr-defined]
    setup.configure(example, setup.Choices("dev", "minimal", False))
    assert example.get("FRONTEND_HOST") == "http://192.168.1.10:5173"  # type: ignore[attr-defined]
    setup.configure(example, setup.Choices("prod", "minimal", False))
    assert example.get("FRONTEND_HOST") == "http://localhost:8000"  # type: ignore[attr-defined]


def test_the_published_port_follows_a_local_address(
    setup: ModuleType, example: object
) -> None:
    setup.configure(
        example, setup.Choices("prod", "minimal", False, host="http://localhost:9000")
    )
    assert example.get("APP_PORT") == "9000"  # type: ignore[attr-defined]
    assert example.lines.count("APP_PORT=9000") == 1  # type: ignore[attr-defined]
    assert not any(line.startswith("# APP_PORT") for line in example.lines)  # type: ignore[attr-defined]
    setup.configure(
        example,
        setup.Choices("prod", "minimal", False, host="https://data.example.com"),
    )
    assert example.get("APP_PORT") == "9000"  # type: ignore[attr-defined]


def test_managed_services_add_their_file(setup: ModuleType, example: object) -> None:
    setup.configure(example, setup.Choices("prod", "standard", True))
    assert example.get("COMPOSE_FILE") == (  # type: ignore[attr-defined]
        "compose.yml,compose.prod.yml,compose.services.yml"
    )
    assert example.get("SERVICES_ENABLED") == "true"  # type: ignore[attr-defined]
    assert example.get("SERVICE_NETWORK") == "dataplayer_default"  # type: ignore[attr-defined]
    args = setup.parse_args(["--yes"])
    assert setup.defaults_from(example, args).services is True
    assert (
        setup.defaults_from(example, setup.parse_args(["--disable-services"])).services
        is False
    )


def test_a_rerun_without_flags_keeps_mode_and_preset(
    setup: ModuleType, example: object
) -> None:
    setup.configure(example, setup.Choices("prod", "standard", False))
    defaults = setup.defaults_from(example, setup.parse_args([]))
    assert (defaults.mode, defaults.preset) == ("prod", "standard")
    fresh = setup.defaults_from(None, setup.parse_args([]))
    assert (fresh.mode, fresh.preset) == ("prod", "minimal")
    dev = setup.defaults_from(None, setup.parse_args(["--mode", "dev"]))
    assert dev.preset == "full"


def test_caddy_serves_https_and_keeps_the_plain_port_local(
    setup: ModuleType, example: object
) -> None:
    host = "https://data.example.com"
    setup.configure(example, setup.Choices("prod", "full", False, host=host, front="caddy"))
    assert example.get("COMPOSE_PROFILES") == "cache,meaning,https"  # type: ignore[attr-defined]
    assert example.get("APP_PORT") == "127.0.0.1:8000"  # type: ignore[attr-defined]
    assert setup.current_preset(example) == "full"
    # A rerun without a choice keeps it, and so does one that only changes the preset.
    setup.configure(example, setup.Choices("prod", "minimal", False))
    assert example.get("COMPOSE_PROFILES") == "https"  # type: ignore[attr-defined]
    assert setup.defaults_from(example, setup.parse_args([])).front == "caddy"
    setup.configure(example, setup.Choices("dev", "minimal", False))
    assert example.get("COMPOSE_PROFILES") == ""  # type: ignore[attr-defined]


def test_a_proxy_of_ones_own_starts_no_caddy(setup: ModuleType, example: object) -> None:
    host = "https://data.example.com"
    setup.configure(example, setup.Choices("prod", "minimal", False, host=host, front="caddy"))
    setup.configure(example, setup.Choices("prod", "minimal", False, front="own"))
    assert example.get("COMPOSE_PROFILES") == ""  # type: ignore[attr-defined]
    # The proxy may sit on this machine, so the port stays where it was.
    assert example.get("APP_PORT") == "127.0.0.1:8000"  # type: ignore[attr-defined]
    assert setup.current_front(example) == "own"


def test_an_address_without_https_has_no_front(setup: ModuleType, example: object) -> None:
    setup.configure(
        example,
        setup.Choices("prod", "minimal", False, host="https://data.example.com", front="caddy"),
    )
    setup.configure(
        example, setup.Choices("prod", "minimal", False, host="http://192.168.1.10:8000")
    )
    assert example.get("COMPOSE_PROFILES") == ""  # type: ignore[attr-defined]
    # People open the port itself again, so it is no longer bound to this machine.
    assert example.get("APP_PORT") == "8000"  # type: ignore[attr-defined]
    setup.configure(
        example, setup.Choices("prod", "minimal", False, host="https://localhost", front="caddy")
    )
    assert example.get("COMPOSE_PROFILES") == ""  # type: ignore[attr-defined]


def test_the_wizard_offers_caddy_for_an_https_address(
    setup: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    # mode prod, preset minimal, email, generated password, address, Caddy by
    # Enter, no services, write.
    answer(monkeypatch, "1", "1", "owner@example.com", "1", "https://data.example.com", "", "n", "y")
    assert run(setup, tmp_path) == 0
    env = setup.EnvFile.load(tmp_path / ".env")
    assert env.get("COMPOSE_PROFILES") == "https"
    assert env.get("APP_PORT") == "127.0.0.1:8000"
    output = capsys.readouterr().out
    assert "who serves HTTPS" in output
    assert "ports 80 and 443" in output


def test_the_wizard_does_not_ask_about_https_for_a_local_address(
    setup: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answer(monkeypatch, "1", "1", "owner@example.com", "1", "http://localhost:8000", "n", "y")
    assert run(setup, tmp_path) == 0
    assert "who serves HTTPS" not in capsys.readouterr().out


def test_the_wizard_allows_services_by_default_on_this_machine_alone(
    setup: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    # mode prod, preset minimal, email, generated password, address, services
    # by Enter, write.
    answer(monkeypatch, "1", "1", "owner@example.com", "1", "http://localhost:8000", "", "y")
    assert run(setup, tmp_path) == 0
    assert setup.EnvFile.load(tmp_path / ".env").get("SERVICES_ENABLED") == "true"
    assert "allow managed services [Y/n]" in capsys.readouterr().out

    remote = tmp_path / "remote"
    remote.mkdir()
    answer(monkeypatch, "1", "1", "owner@example.com", "1", "http://192.168.1.10:8000", "", "y")
    assert run(setup, remote) == 0
    assert setup.EnvFile.load(remote / ".env").get("SERVICES_ENABLED") == "false"
    assert "allow managed services [y/N]" in capsys.readouterr().out


def test_an_earlier_no_to_services_is_kept_on_this_machine(
    setup: ModuleType, example: object
) -> None:
    assert setup.defaults_from(None, setup.parse_args([])).services is None
    # A copied example is development, which decided nothing about them.
    assert setup.defaults_from(example, setup.parse_args([])).services is None
    setup.configure(example, setup.Choices("prod", "minimal", False))
    decided = setup.defaults_from(example, setup.parse_args([])).services
    assert decided is False
    assert setup.default_services(decided, "http://localhost:8000") is False
    assert setup.default_services(None, "http://127.0.0.1:8000") is True
    assert setup.default_services(None, "https://data.example.com") is False


def test_an_unattended_first_run_allows_no_services(setup: ModuleType, tmp_path: Path) -> None:
    assert run(setup, tmp_path, "--mode", "prod", "--yes") == 0
    env = setup.EnvFile.load(tmp_path / ".env")
    assert env.get("SERVICES_ENABLED") == "false"
    assert env.get("COMPOSE_FILE") == "compose.yml,compose.prod.yml"


def test_the_https_flag_chooses_without_asking(setup: ModuleType, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        EXAMPLE.read_text(encoding="utf-8").replace(
            "FRONTEND_HOST=http://localhost:5173", "FRONTEND_HOST=https://data.example.com"
        ),
        encoding="utf-8",
    )
    assert run(setup, tmp_path, "--mode", "prod", "--https", "caddy", "--yes") == 0
    env = setup.EnvFile.load(tmp_path / ".env")
    assert env.get("COMPOSE_PROFILES") == "https"
    assert run(setup, tmp_path, "--https", "own", "--yes") == 0
    assert setup.EnvFile.load(tmp_path / ".env").get("COMPOSE_PROFILES") == ""


def test_a_rerun_keeps_a_compose_file_of_the_installations_own(
    setup: ModuleType, example: object
) -> None:
    example.set("COMPOSE_FILE", "compose.yml,compose.prod.yml,compose.traefik.yml")  # type: ignore[attr-defined]
    setup.configure(example, setup.Choices("prod", "minimal", True))
    assert example.get("COMPOSE_FILE") == (  # type: ignore[attr-defined]
        "compose.yml,compose.prod.yml,compose.services.yml,compose.traefik.yml"
    )
    setup.configure(example, setup.Choices("prod", "minimal", False))
    assert example.get("COMPOSE_FILE") == "compose.yml,compose.prod.yml,compose.traefik.yml"  # type: ignore[attr-defined]


def test_set_takes_over_a_commented_entry(example: object) -> None:
    example.comment_out("FASTAPI_ENV")  # type: ignore[attr-defined]
    example.set("FASTAPI_ENV", "development")  # type: ignore[attr-defined]
    assert example.lines.count("FASTAPI_ENV=development") == 1  # type: ignore[attr-defined]


def test_changes_name_every_line_and_warn_about_a_started_stack(
    setup: ModuleType, example: object
) -> None:
    before = example.copy()  # type: ignore[attr-defined]
    setup.configure(example, setup.Choices("prod", "minimal", False))
    changed = {change.name for change in setup.changes(before, example)}
    assert {
        "SECRET_KEY",
        "POSTGRES_PASSWORD",
        "COMPOSE_FILE",
        "FRONTEND_HOST",
    } <= changed
    assert "PROJECT_NAME" not in changed
    found = setup.changes(before, example)
    assert setup.warnings(found, existed=False) == []
    warned = " ".join(setup.warnings(found, existed=True))
    assert "POSTGRES_PASSWORD" in warned and "FIRST_SUPERUSER_PASSWORD" in warned


def test_an_unattended_run_writes_and_a_second_keeps_the_secrets(
    setup: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        run(setup, tmp_path, "--mode", "dev", "--superuser", "owner@example.com") == 0
    )
    first = setup.EnvFile.load(tmp_path / ".env")
    assert first.get("FIRST_SUPERUSER") == "owner@example.com"
    assert first.get("COMPOSE_PROFILES") == "cache,meaning"
    assert (tmp_path / "frontend.env").exists()
    output = capsys.readouterr().out
    assert "docker compose up -d --build" in output
    # Not a terminal: the generated password stays in .env alone.
    assert first.get("FIRST_SUPERUSER_PASSWORD") not in output

    assert run(setup, tmp_path, "--mode", "prod", "--preset", "minimal", "--yes") == 0
    second = setup.EnvFile.load(tmp_path / ".env")
    for name in setup.SECRETS:
        assert second.get(name) == first.get(name)
    assert second.get("FIRST_SUPERUSER") == "owner@example.com"
    assert "POSTGRES_PASSWORD" not in capsys.readouterr().out
    assert sorted(path.name for path in tmp_path.iterdir()) == [".env", "frontend.env"]


def test_the_wizard_asks_and_writes_after_a_yes(
    setup: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    # mode prod, preset standard, email, type a password, address, a proxy of
    # one's own, no services, write.
    answer(
        monkeypatch,
        "1",
        "2",
        "owner@example.com",
        "2",
        "https://data.example.com/",
        "2",
        "n",
        "y",
    )
    monkeypatch.setattr(setup.getpass, "getpass", lambda _prompt="": "a long secret")
    assert run(setup, tmp_path) == 0
    env = setup.EnvFile.load(tmp_path / ".env")
    assert env.get("COMPOSE_PROFILES") == "cache"
    assert env.get("FRONTEND_HOST") == "https://data.example.com"
    assert env.get("FIRST_SUPERUSER_PASSWORD") == "a long secret"
    assert "FIRST_SUPERUSER_PASSWORD='a long secret'" in env.lines
    # Listed before it is written, the secrets by name alone.
    output = capsys.readouterr().out
    assert "FRONTEND_HOST" in output and "a long secret" not in output


def test_declining_writes_nothing(
    setup: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copy(EXAMPLE, tmp_path / ".env")
    before = (tmp_path / ".env").read_bytes()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    # A copied example is development: mode, preset, email, password, write.
    answer(monkeypatch, "", "", "", "", "n")
    assert run(setup, tmp_path) == 1
    assert (tmp_path / ".env").read_bytes() == before


def test_a_half_erased_letter_does_not_spoil_an_answer(
    setup: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # "н", Backspace, "y" on a terminal without IUTF8: one byte of the "н"
    # stays and arrives as a surrogate the screen never showed.
    answer(monkeypatch, "\udcd0y", "\udcd0n", "\udcd02", "\udcd0owner@example.com")
    assert setup.ask_confirm("allow managed services", default_yes=False) is True
    assert setup.ask_confirm("allow managed services") is False
    assert setup.ask_choice("preset", setup.PRESETS, "minimal", {}) == "standard"
    assert setup.ask_text("superuser email", "admin@example.com") == "owner@example.com"
    assert "answer y or n" not in capsys.readouterr().out


def test_a_half_erased_letter_does_not_reach_a_password(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    typed = iter(["2", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(typed))
    secrets = iter(["a long\udcd1 secret ", "a long secret "])
    monkeypatch.setattr(setup.getpass, "getpass", lambda _prompt="": next(secrets))
    assert setup.ask_password() == "a long secret "


def test_a_choice_takes_numbers_alone(
    setup: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    answer(monkeypatch, "standart", "9", "3")
    assert setup.ask_choice("preset", setup.PRESETS, "minimal", {}) == "full"
    assert "enter a number" in capsys.readouterr().out
