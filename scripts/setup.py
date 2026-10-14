"""First-run setup for DataPlayer.

In a terminal and without --preset, --mode or --yes it asks every first-run
question; otherwise it runs from its flags. Either way it writes one `.env`
that every later `docker compose` command follows: COMPOSE_FILE carries the
mode, COMPOSE_PROFILES the preset. Secrets are filled only where `.env` holds
nothing or the `changethis` placeholder; a value somebody chose is kept.

Presets, on top of db, prestart, the backend, metrics and search-keeper:
    minimal   no profile; the process-local memory cache.
    standard  profile `cache`: the shared Redis read cache (D103).
    full      profiles `cache` and `meaning`: plus search by meaning (D220).

Development helpers — Adminer, Mailcatcher, a test Redis and SSH server, the
E2E runner — stay behind the `tools`/`e2e` profiles whatever the preset, and
start on request with `docker compose --profile tools up -d`.

Usage:
    python scripts/setup.py [--preset {minimal,standard,full}]
                            [--mode {dev,prod}] [--enable-services]
                            [--no-run] [--yes]
"""

from __future__ import annotations

import argparse
import base64
import functools
import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
FRONTEND_ENV_PATH = REPO_ROOT / "frontend" / ".env"
FRONTEND_ENV_EXAMPLE_PATH = REPO_ROOT / "frontend" / ".env.example"

PLACEHOLDER = "changethis"

MODES = ("prod", "dev")
PRESETS = ("minimal", "standard", "full")
PROFILES = {"minimal": (), "standard": ("cache",), "full": ("cache", "meaning")}
COMPOSE_FILES = {
    "dev": ("compose.yml", "compose.override.yml"),
    "prod": ("compose.yml", "compose.prod.yml"),
}
SERVICES_FILE = "compose.services.yml"

# Every one is generated whatever the preset: Compose interpolates the dormant
# cache service too, and the settings reject a placeholder key even while the
# memory cache never reads it. So switching presets never touches a secret.
KEYS = ("SECRET_KEY", "CONNECTOR_SECRET_KEY", "QUERY_CONTENT_KEY", "AI_CONTENT_KEY", "DATA_CACHE_SECRET_KEY")
PASSWORDS = ("POSTGRES_PASSWORD", "DATA_CACHE_REDIS_PASSWORD", "FIRST_SUPERUSER_PASSWORD")

DEV_HOST = "http://localhost:5173"
PROD_HOST = "http://localhost:8000"
# Where the backend reaches the local meaning model; the full preset fills it
# in, every other preset clears it, so the search never aims at a model that
# is not running.
EMBEDDER_URL = "http://embedder:80"
# Development serves the interface from Vite, so only what the interface
# talks to is started; Adminer, Mailcatcher, the test Redis/SSH servers and
# the E2E runner stay behind the `tools`/`e2e` profiles (or an explicit
# service name) on request.
DEV_TARGETS = ("backend", "metrics", "search-keeper")
# `depends_on.required`, which keeps the backend starting without the cache.
MIN_COMPOSE = (2, 20)


@functools.lru_cache(maxsize=1)
def _use_color() -> bool:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    if os.name != "nt":
        return True
    # A Windows console prints escape codes as text until asked not to.
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]  # Windows only
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError):
        return False


def _paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _use_color() else text


def bold(text: str) -> str:
    return _paint("1", text)


def dim(text: str) -> str:
    return _paint("2", text)


def green(text: str) -> str:
    return _paint("32", text)


def yellow(text: str) -> str:
    return _paint("33", text)


def red(text: str) -> str:
    return _paint("31", text)


def cyan(text: str) -> str:
    return _paint("36", text)


def rule(width: int = 56) -> str:
    # ASCII: the Windows console encoding has no line-drawing characters.
    return dim("-" * width)


def bare(value: str | None) -> str:
    if value is None:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


@dataclass
class EnvFile:
    """Lines of a `.env` file, edited in place so its comments survive."""

    lines: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> EnvFile:
        return cls(path.read_text(encoding="utf-8").splitlines())

    def save(self, path: Path) -> None:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8", newline="\n")

    @staticmethod
    def _split(line: str) -> tuple[str, str] | None:
        if line.lstrip().startswith("#") or "=" not in line:
            return None
        name, _, value = line.partition("=")
        name = name.strip()
        if not name or " " in name:
            return None
        return name, value.strip()

    def _index(self, name: str) -> int | None:
        for index, line in enumerate(self.lines):
            split = self._split(line)
            if split is not None and split[0] == name:
                return index
        return None

    def get(self, name: str) -> str | None:
        index = self._index(name)
        if index is None:
            return None
        split = self._split(self.lines[index])
        return bare(split[1]) if split else None

    def is_unset(self, name: str) -> bool:
        return self.get(name) in {None, "", PLACEHOLDER}

    def set(self, name: str, value: str, *, literal: bool = False) -> bool:
        """Set an entry; True when it changed. `literal` single-quotes it.

        Compose and python-dotenv both expand `$` and cut at ` #` in an
        unquoted or double-quoted value, and neither does in single quotes.

        When no active entry exists but a commented one does (for example
        FASTAPI_ENV after a prod run commented it out), the commented line is
        replaced in place rather than appended as a duplicate.
        """
        rendered = f"'{value}'" if literal else value
        index = self._index(name)
        if index is None:
            for commented, line in enumerate(self.lines):
                if re.match(rf"\s*#\s*{re.escape(name)}\s*=", line):
                    self.lines[commented] = f"{name}={rendered}"
                    return True
            self.lines.append(f"{name}={rendered}")
            return True
        if self.lines[index] == f"{name}={rendered}":
            return False
        self.lines[index] = f"{name}={rendered}"
        return True

    def comment_out(self, name: str) -> bool:
        index = self._index(name)
        if index is None:
            return False
        self.lines[index] = "# " + self.lines[index]
        return True


def generate_key() -> str:
    """urlsafe base64 of 32 bytes: what every AES-GCM key is checked against."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def generate_password() -> str:
    # No `=` padding: it lands inside DATABASE_URL and DATA_CACHE_REDIS_URL.
    return secrets.token_urlsafe(24)


@dataclass
class Choices:
    mode: str
    preset: str
    services: bool
    email: str | None = None
    password: str | None = None
    host: str | None = None


@dataclass
class Report:
    generated: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def track(self, name: str, changed: bool) -> None:
        if changed and name not in self.changed:
            self.changed.append(name)


def current_mode(env: EnvFile) -> str | None:
    files = env.get("COMPOSE_FILE") or ""
    if "compose.prod.yml" in files:
        return "prod"
    if "compose.override.yml" in files:
        return "dev"
    return None


def current_preset(env: EnvFile) -> str | None:
    profiles = {p.strip() for p in (env.get("COMPOSE_PROFILES") or "").split(",") if p.strip()}
    if "meaning" in profiles:
        return "full"
    if "cache" in profiles:
        return "standard"
    return "minimal" if env.get("COMPOSE_PROFILES") is not None else None


def default_preset(mode: str) -> str:
    return "full" if mode == "dev" else "minimal"


def is_dev_origin(value: str | None) -> bool:
    """Whether an address is a Vite dev server the browser runs pages from.

    The backend accepts calls from FRONTEND_HOST alone (CORS), so in
    development that must be the Vite origin: anything else — the prod
    address left by an earlier run, for example — locks the interface out.
    A custom dev address (a LAN host Vite listens on) still counts.
    """
    if not value:
        return False
    try:
        return urlsplit(value).port == 5173
    except ValueError:
        return False


def configure(env: EnvFile, choices: Choices, report: Report) -> None:
    """Bring `.env` in line with the choices; a chosen secret is never replaced."""
    for name in KEYS + PASSWORDS:
        if name == "FIRST_SUPERUSER_PASSWORD" and choices.password is not None:
            env.set(name, choices.password, literal=True)
            report.generated.append(f"{name} (chosen in setup)")
        elif env.is_unset(name):
            env.set(name, generate_key() if name in KEYS else generate_password())
            report.generated.append(name)

    if choices.email is not None:
        report.track("FIRST_SUPERUSER", env.set("FIRST_SUPERUSER", choices.email))

    files = list(COMPOSE_FILES[choices.mode])
    if choices.mode == "prod" and choices.services:
        files.append(SERVICES_FILE)
    report.track("COMPOSE_PATH_SEPARATOR", env.set("COMPOSE_PATH_SEPARATOR", ","))
    report.track("COMPOSE_FILE", env.set("COMPOSE_FILE", ",".join(files)))
    report.track("COMPOSE_PROFILES", env.set("COMPOSE_PROFILES", ",".join(PROFILES[choices.preset])))
    backend = "redis" if "cache" in PROFILES[choices.preset] else "memory"
    report.track("DATA_CACHE_BACKEND", env.set("DATA_CACHE_BACKEND", backend))
    if "meaning" in PROFILES[choices.preset]:
        if env.is_unset("EMBEDDINGS_URL"):
            report.track("EMBEDDINGS_URL", env.set("EMBEDDINGS_URL", EMBEDDER_URL))
    elif not env.is_unset("EMBEDDINGS_URL"):
        env.set("EMBEDDINGS_URL", "")
        report.changed.append("EMBEDDINGS_URL (cleared)")

    if choices.mode == "dev":
        report.track("FASTAPI_ENV", env.set("FASTAPI_ENV", "development"))
        # The interface is Vite's in development, and the API accepts calls
        # from FRONTEND_HOST alone. A stale address — the prod one an earlier
        # run wrote, for example — is reset to the dev server; only an
        # address that already points at a Vite origin is kept.
        if env.is_unset("FRONTEND_HOST") or not is_dev_origin(env.get("FRONTEND_HOST")):
            report.track("FRONTEND_HOST", env.set("FRONTEND_HOST", DEV_HOST))
        if env.get("DATA_CACHE_DEPLOYMENT") in {None, "", "production"}:
            report.track("DATA_CACHE_DEPLOYMENT", env.set("DATA_CACHE_DEPLOYMENT", "development"))
        return

    # Without FASTAPI_ENV a placeholder secret stops the start.
    if env.comment_out("FASTAPI_ENV"):
        report.changed.append("FASTAPI_ENV (commented out)")
    host = choices.host
    stored = env.get("FRONTEND_HOST")
    if host is None and (not stored or is_dev_origin(stored)):
        host = PROD_HOST
    if host is not None:
        report.track("FRONTEND_HOST", env.set("FRONTEND_HOST", host))
    if env.get("DATA_CACHE_DEPLOYMENT") in {None, "", "development"}:
        report.track("DATA_CACHE_DEPLOYMENT", env.set("DATA_CACHE_DEPLOYMENT", "production"))
    report.track("SERVICES_ENABLED", env.set("SERVICES_ENABLED", "true" if choices.services else "false"))
    if choices.services:
        # The names Compose gives this project's network and volume (`name:`
        # in compose.yml); the override sets the same pair for development.
        if env.is_unset("SERVICE_NETWORK"):
            report.track("SERVICE_NETWORK", env.set("SERVICE_NETWORK", "dataplayer_default"))
        if env.is_unset("SERVICE_STORAGE_VOLUME"):
            report.track("SERVICE_STORAGE_VOLUME", env.set("SERVICE_STORAGE_VOLUME", "dataplayer_user-storage"))


def compose_command(choices: Choices) -> list[str]:
    """What starts the stack. Files and profiles come from `.env`."""
    command = ["docker", "compose", "up", "-d", "--build"]
    if choices.mode == "dev":
        command += list(DEV_TARGETS)
        if "meaning" in PROFILES[choices.preset]:
            command.append("embedder")
    return command


def compose_environment() -> dict[str, str]:
    # A variable in the shell outranks `.env` for Compose, so a stale export
    # would start something other than what was just written.
    blocked = {"COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PATH_SEPARATOR"}
    return {name: value for name, value in os.environ.items() if name not in blocked}


def compose_problem() -> str | None:
    """Why the stack cannot be started from here, or nothing."""
    if shutil.which("docker") is None:
        return "docker is not on PATH: install Docker, then run this again."
    try:
        result = subprocess.run(
            ["docker", "compose", "version", "--short"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "`docker compose version` did not answer: is Docker running?"
    match = re.match(r"v?(\d+)\.(\d+)", result.stdout.strip())
    if result.returncode != 0 or match is None:
        return "Docker Compose v2 is required (`docker compose`, not `docker-compose`)."
    if (int(match.group(1)), int(match.group(2))) < MIN_COMPOSE:
        found = result.stdout.strip()
        return f"Docker Compose {found} is too old: 2.20 or newer is required."
    return None


# --- Questions ---------------------------------------------------------------


def ask_choice(prompt: str, options: tuple[str, ...], default: str) -> str:
    numbered = ", ".join(f"{index + 1}) {option}" for index, option in enumerate(options))
    print(f"{prompt}: {numbered}")
    default_number = options.index(default) + 1
    while True:
        answer = input(f"number [{default_number}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print(red(f"enter a number from 1 to {len(options)}"))


def ask_text(prompt: str, default: str) -> str:
    answer = input(f"{prompt} [{default}]: ").strip()
    return answer or default


def ask_confirm(prompt: str, default_yes: bool = True) -> bool:
    hint = "Y/n" if default_yes else "y/N"
    while True:
        answer = input(f"{prompt} [{hint}]: ").strip().lower()
        if not answer:
            return default_yes
        if answer in {"y", "yes", "n", "no"}:
            return answer.startswith("y")
        print(red("answer y or n."))


def valid_email(value: str) -> bool:
    return re.fullmatch(r"[^@\s'\"$#\\]+@[^@\s'\"$#\\]+\.[^@\s'\"$#\\]+", value) is not None


def valid_host(value: str) -> bool:
    return re.fullmatch(r"https?://[^/\s'\"$#\\]+", value) is not None


def password_problem(value: str) -> str | None:
    if not 8 <= len(value) <= 128:
        return "between 8 and 128 characters."
    # Written single-quoted into `.env`, where neither has an escape.
    if "'" in value or "\\" in value:
        return "no single quote and no backslash."
    return None


def read_password(prompt: str) -> str:
    try:
        return getpass.getpass(f"{prompt}: ")
    except (EOFError, OSError):
        print(yellow("note: the terminal echoes this password."))
        return input(f"{prompt}: ")


def ask_superuser_password(env: EnvFile) -> str | None:
    """A new superuser password, or nothing when the stored one stays."""
    if not env.is_unset("FIRST_SUPERUSER_PASSWORD"):
        print(dim("superuser password: the one in .env stays."))
        return None
    choice = ask_choice("superuser password", ("generate", "type my own"), "generate")
    if choice == "generate":
        return None
    while True:
        first = read_password("new password")
        problem = password_problem(first)
        if problem is not None:
            print(red(problem))
            continue
        if read_password("repeat it") != first:
            print(red("the two do not match."))
            continue
        return first


def run_wizard(env: EnvFile) -> Choices | None:
    """Ask every first-run question; None when the person declines at the end."""
    print()
    print(bold("DataPlayer setup"))
    print("Enter keeps the value in brackets.")
    print(rule())
    mode = ask_choice(
        "run it for use (prod) or develop it (dev)", MODES, current_mode(env) or "prod"
    )
    print(dim("minimal: the application alone.  standard: plus a shared read cache."))
    print(dim("full: plus search by meaning through a local model (downloads it once)."))
    preset = ask_choice("preset", PRESETS, current_preset(env) or default_preset(mode))

    email_default = env.get("FIRST_SUPERUSER") or "admin@example.com"
    while True:
        email = ask_text("superuser email", email_default)
        if valid_email(email):
            break
        print(red("that does not look like an email address."))
    password = ask_superuser_password(env)

    host: str | None = None
    services = False
    if mode == "prod":
        stored = env.get("FRONTEND_HOST")
        host_default = stored if stored and not is_dev_origin(stored) else PROD_HOST
        while True:
            host = ask_text("the address people open", host_default).rstrip("/")
            if valid_host(host):
                break
            print(red("an address like http://localhost:8000 or https://data.example.com"))
        print(dim("managed services: the server starts databases in containers of its own."))
        services = ask_confirm(
            "allow managed services", default_yes=env.get("SERVICES_ENABLED") == "true"
        )
        if services:
            print(yellow("warning: a process that reaches the container runtime reaches the host."))
    else:
        stored = env.get("FRONTEND_HOST")
        if stored and not is_dev_origin(stored):
            print(dim(f"the API origin returns to the Vite dev server ({DEV_HOST});"))
            print(dim("the previous address stays in .env.bak."))

    print()
    print(f"  mode: {cyan(mode)}   preset: {cyan(preset)}   superuser: {email}")
    if mode == "prod":
        print(f"  address: {host}   managed services: {'on' if services else 'off'}")
    print()
    if not ask_confirm("write .env and continue"):
        print("nothing was written.")
        return None
    return Choices(mode, preset, services, email=email, password=password, host=host)


# --- Running -----------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up and start DataPlayer.")
    parser.add_argument("--preset", choices=PRESETS)
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument(
        "--enable-services",
        action="store_true",
        help="let a running installation start containers (D82, D86).",
    )
    parser.add_argument("--no-run", action="store_true", help="write .env only.")
    parser.add_argument("--yes", action="store_true", help="ask nothing.")
    return parser.parse_args(argv)


def choices_from_flags(args: argparse.Namespace) -> Choices:
    mode = args.mode or "dev"
    return Choices(mode, args.preset or default_preset(mode), args.enable_services)


def print_summary(choices: Choices, report: Report, command: list[str]) -> None:
    print()
    print(bold("Setup summary"))
    print(rule())
    print(f"  mode: {cyan(choices.mode)}   preset: {cyan(choices.preset)}")
    if report.generated:
        print(green("  generated: ") + ", ".join(report.generated))
    if report.changed:
        print("  written: " + ", ".join(report.changed))
    for note in report.notes:
        print(dim(f"  note: {note}"))
    print(f"  start: {' '.join(command)}")
    print(rule())


def print_next_steps(choices: Choices, env: EnvFile, report: Report) -> None:
    if choices.mode == "dev":
        print("interface: http://localhost:5173   api: http://localhost:8000/docs")
        print("then: cd frontend && bun install && bun run dev")
        print("examples for the connections panel: bun run seed:connectors")
        print(dim("helpers on request: docker compose --profile tools up -d"))
        print(dim("(Adminer, Mailcatcher, a test Redis and SSH server)"))
    else:
        print(f"interface: {env.get('FRONTEND_HOST')}   sign in as {env.get('FIRST_SUPERUSER')}")
        print(dim("the port speaks plain HTTP: reach it from outside only through"))
        print(dim("a reverse proxy that terminates HTTPS."))
    if choices.preset == "full":
        print(dim("the embedder downloads its model on its first start."))
    if "FIRST_SUPERUSER_PASSWORD" in report.generated:
        # Kept off logs: a run without a terminal finds it in .env alone.
        if sys.stdout.isatty():
            password = env.get("FIRST_SUPERUSER_PASSWORD")
            print(green(f"superuser password: {password}") + " (also in .env)")
        else:
            print("superuser password: FIRST_SUPERUSER_PASSWORD in .env")
    print("every later `docker compose` command follows .env; run this again to change it.")


def main(
    argv: list[str] | None = None,
    env_path: Path = ENV_PATH,
    frontend_env_path: Path = FRONTEND_ENV_PATH,
) -> int:
    args = parse_args(argv)
    existed = env_path.exists()
    # Read, not copied: nothing reaches the disk before the answers do.
    env = EnvFile.load(env_path if existed else ENV_EXAMPLE_PATH)

    interactive = sys.stdin.isatty() and not (args.preset or args.mode or args.yes)
    if interactive:
        choices = run_wizard(env)
        if choices is None:
            return 1
    else:
        choices = choices_from_flags(args)
        if sys.stdin.isatty() and not args.yes:
            print(f"mode: {choices.mode}   preset: {choices.preset}")
            if not ask_confirm("write .env and continue"):
                print("nothing was written.")
                return 1

    report = Report()
    configure(env, choices, report)
    if existed:
        backup = env_path.with_name(env_path.name + ".bak")
        shutil.copy(env_path, backup)
        report.notes.append(f"the previous file is in {backup.name}")
    else:
        report.notes.append(f"{env_path.name} created from {ENV_EXAMPLE_PATH.name}")
    env.save(env_path)
    if choices.mode == "dev" and not frontend_env_path.exists():
        shutil.copy(FRONTEND_ENV_EXAMPLE_PATH, frontend_env_path)
        report.notes.append("frontend/.env created from frontend/.env.example")

    command = compose_command(choices)
    print_summary(choices, report, command)
    print_next_steps(choices, env, report)
    if args.no_run or os.environ.get("SETUP_CONTAINER") == "1":
        if os.environ.get("SETUP_CONTAINER") == "1":
            print("running in the setup container: start the stack on the host")
            print("with: docker compose up -d --build")
        return 0

    problem = compose_problem()
    if problem is not None:
        print(red(problem))
        print(f".env is written; start it later with: {' '.join(command)}")
        return 1
    print()
    result = subprocess.run(command, cwd=REPO_ROOT, env=compose_environment(), check=False)
    if result.returncode != 0:
        print(red(f"start failed with exit code {result.returncode}."))
        print("inspect it with: docker compose logs prestart backend")
        return result.returncode
    print(green("started."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
