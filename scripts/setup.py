"""First-run setup for DataPlayer: writes `.env`, starts nothing.

Run in a container, so a machine needs Docker alone:

    docker compose -f compose.setup.yml run --rm setup
    docker compose up -d --build

`python scripts/setup.py` on the host does the same. In a terminal it asks
what it needs; with --yes, or without a terminal, it takes its flags and the
current `.env` instead. Before writing it shows every line it will change and
asks to confirm.

The written `.env` is what every later `docker compose` command follows:
COMPOSE_FILE carries the mode, COMPOSE_PROFILES the preset.

    minimal   no profile: the memory read cache, no search by meaning.
    standard  profile `cache`: the shared Redis read cache (D103).
    full      profiles `cache,meaning`: plus search by meaning (D220).

A secret is generated only where `.env` holds nothing or `changethis`; one
already there is never replaced.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import os
import re
import secrets
import shutil
import sys
from dataclasses import dataclass
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
# compose.prod.yml's Caddy. Not a preset: whether it runs depends on the
# address and on what else holds ports 80 and 443, which only the person knows.
HTTPS_PROFILE = "https"
FRONTS = ("caddy", "own")
COMPOSE_FILES = {
    "dev": ("compose.yml", "compose.override.yml"),
    "prod": ("compose.yml", "compose.prod.yml"),
}
SERVICES_FILE = "compose.services.yml"

# All of them whatever the preset: Compose interpolates the cache service even
# while its profile is off, and the settings refuse a placeholder cache key
# even while the memory cache never reads it.
KEYS = (
    "SECRET_KEY",
    "CONNECTOR_SECRET_KEY",
    "QUERY_CONTENT_KEY",
    "AI_CONTENT_KEY",
    "DATA_CACHE_SECRET_KEY",
)
PASSWORDS = ("POSTGRES_PASSWORD", "DATA_CACHE_REDIS_PASSWORD", "FIRST_SUPERUSER_PASSWORD")
SECRETS = KEYS + PASSWORDS

# Both are read only when the stack is created: PostgreSQL keeps the password
# its volume was initialised with, prestart keeps an existing superuser.
FIXED_AT_FIRST_START = {
    "POSTGRES_PASSWORD": "the database keeps the password it was created with",
    "FIRST_SUPERUSER_PASSWORD": "an existing superuser keeps the password it has",
}

DEV_HOST = "http://localhost:5173"
PROD_HOST = "http://localhost:8000"
EMBEDDER_URL = "http://embedder:80"
LOCAL_HOSTS = {"localhost", "127.0.0.1"}

PRESET_HELP = {
    "minimal": "the application alone",
    "standard": "plus a shared read cache in Redis",
    "full": "plus search by meaning; downloads a model once",
}
FRONT_HELP = {
    "caddy": "DataPlayer gets and renews the certificate itself",
    "own": "a proxy already on this machine or network does it",
}
MODE_HELP = {
    "prod": "run it: the interface on one port, no samples",
    "dev": "develop it: sample data, the interface from Bun",
}


# --- Output ------------------------------------------------------------------


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


COLOR = _use_color()


def paint(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def bold(text: str) -> str:
    return paint("1", text)


def dim(text: str) -> str:
    return paint("2", text)


def green(text: str) -> str:
    return paint("32", text)


def yellow(text: str) -> str:
    return paint("33", text)


def red(text: str) -> str:
    return paint("31", text)


# --- .env --------------------------------------------------------------------


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


class EnvFile:
    """Lines of a `.env` file, edited in place so its comments survive."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    @classmethod
    def load(cls, path: Path) -> EnvFile:
        return cls(path.read_text(encoding="utf-8").splitlines())

    def copy(self) -> EnvFile:
        return EnvFile(list(self.lines))

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"

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

    def names(self) -> list[str]:
        return [split[0] for line in self.lines if (split := self._split(line))]

    def get(self, name: str) -> str | None:
        index = self._index(name)
        if index is None:
            return None
        split = self._split(self.lines[index])
        return unquote(split[1]) if split else None

    def is_unset(self, name: str) -> bool:
        return self.get(name) in {None, "", PLACEHOLDER}

    def set(self, name: str, value: str, *, literal: bool = False) -> None:
        """Set an entry; `literal` single-quotes it.

        Compose and python-dotenv both expand `$` and cut at ` #` in an
        unquoted or double-quoted value, and neither does in single quotes.
        With no active entry a commented one (`# APP_PORT=8000`) is taken over
        in place, so a switch back and forth does not grow the file.
        """
        line = f"{name}='{value}'" if literal else f"{name}={value}"
        index = self._index(name)
        if index is None:
            for commented, existing in enumerate(self.lines):
                if re.match(rf"\s*#\s*{re.escape(name)}=", existing):
                    index = commented
                    break
        if index is None:
            self.lines.append(line)
        else:
            self.lines[index] = line

    def comment_out(self, name: str) -> None:
        index = self._index(name)
        if index is not None:
            self.lines[index] = "# " + self.lines[index]


def generate_key() -> str:
    """urlsafe base64 of 32 bytes: what every AES-GCM key is checked against."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def generate_password() -> str:
    # No `=` padding and nothing to encode: it lands inside DATABASE_URL and
    # DATA_CACHE_REDIS_URL.
    return secrets.token_urlsafe(24)


# --- What is being set up ----------------------------------------------------


@dataclass
class Choices:
    mode: str
    preset: str
    services: bool
    email: str | None = None
    password: str | None = None
    host: str | None = None
    # Who serves HTTPS; None keeps what `.env` already says.
    front: str | None = None


def current_mode(env: EnvFile) -> str | None:
    files = env.get("COMPOSE_FILE") or ""
    if "compose.prod.yml" in files:
        return "prod"
    if "compose.override.yml" in files:
        return "dev"
    return None


def current_preset(env: EnvFile) -> str | None:
    profiles = env.get("COMPOSE_PROFILES")
    if profiles is None:
        return None
    names = {p.strip() for p in profiles.split(",")}
    if "meaning" in names:
        return "full"
    return "standard" if "cache" in names else "minimal"


def current_services(env: EnvFile) -> bool:
    return SERVICES_FILE in (env.get("COMPOSE_FILE") or "")


def own_compose_files(env: EnvFile) -> list[str]:
    """The files in COMPOSE_FILE that the setup did not put there."""
    ours = {name for names in COMPOSE_FILES.values() for name in names} | {SERVICES_FILE}
    named = [name.strip() for name in (env.get("COMPOSE_FILE") or "").split(",")]
    return [name for name in named if name and name not in ours]


def needs_front(host: str) -> bool:
    """Whether people open the address over HTTPS on a name of its own."""
    parts = urlsplit(host)
    return parts.scheme == "https" and parts.hostname not in LOCAL_HOSTS


def current_front(env: EnvFile) -> str | None:
    profiles = {p.strip() for p in (env.get("COMPOSE_PROFILES") or "").split(",")}
    if HTTPS_PROFILE in profiles:
        return "caddy"
    return "own" if needs_front(env.get("FRONTEND_HOST") or "") else None


def loopback_port(env: EnvFile) -> str:
    """APP_PORT on this machine alone, so nothing goes around the proxy."""
    port = (env.get("APP_PORT") or "").rsplit(":", 1)[-1] or "8000"
    return f"127.0.0.1:{port}"


def default_preset(mode: str) -> str:
    # Development runs everything the presets cover, so nothing in it is
    # untested by the person changing it.
    return "full" if mode == "dev" else "minimal"


def is_dev_origin(value: str | None) -> bool:
    """Whether an address is a Vite dev server, a LAN one included.

    The API accepts calls from FRONTEND_HOST alone, so in development it must
    be the Vite origin, and a running installation must not keep one.
    """
    if not value:
        return False
    try:
        return urlsplit(value).port == 5173
    except ValueError:
        return False


def local_port(host: str) -> int | None:
    """The port of an address on this machine itself, which APP_PORT must match."""
    parts = urlsplit(host)
    if parts.hostname in LOCAL_HOSTS:
        return parts.port
    return None


def configure(env: EnvFile, choices: Choices) -> None:
    """Bring `.env` in line with the choices. A chosen secret is never replaced."""
    for name in SECRETS:
        if name == "FIRST_SUPERUSER_PASSWORD" and choices.password is not None:
            env.set(name, choices.password, literal=True)
        elif env.is_unset(name):
            env.set(name, generate_key() if name in KEYS else generate_password())
    if choices.email is not None:
        env.set("FIRST_SUPERUSER", choices.email)

    profiles = PROFILES[choices.preset]
    host = choices.host
    if host is None:
        stored = env.get("FRONTEND_HOST")
        host = stored if stored and not is_dev_origin(stored) else PROD_HOST
    front = choices.front or current_front(env)
    caddy = choices.mode == "prod" and needs_front(host) and front == "caddy"
    if caddy:
        profiles += (HTTPS_PROFILE,)
    files = list(COMPOSE_FILES[choices.mode])
    if choices.mode == "prod" and choices.services:
        files.append(SERVICES_FILE)
    if choices.mode == "prod":
        files.extend(own_compose_files(env))
    env.set("COMPOSE_PATH_SEPARATOR", ",")
    env.set("COMPOSE_FILE", ",".join(files))
    env.set("COMPOSE_PROFILES", ",".join(profiles))
    env.set("DATA_CACHE_BACKEND", "redis" if "cache" in profiles else "memory")
    if "meaning" not in profiles:
        # Search never aims at a model that is not running.
        env.set("EMBEDDINGS_URL", "")
    elif env.is_unset("EMBEDDINGS_URL"):
        env.set("EMBEDDINGS_URL", EMBEDDER_URL)

    if choices.mode == "dev":
        env.set("FASTAPI_ENV", "development")
        if not is_dev_origin(env.get("FRONTEND_HOST")):
            env.set("FRONTEND_HOST", DEV_HOST)
        if env.get("DATA_CACHE_DEPLOYMENT") in {None, "", "production"}:
            env.set("DATA_CACHE_DEPLOYMENT", "development")
        # The override mounts the socket and switches services on itself.
        return

    # Without FASTAPI_ENV a placeholder secret stops the start.
    env.comment_out("FASTAPI_ENV")
    env.set("FRONTEND_HOST", host)
    port = local_port(host)
    if port is not None:
        env.set("APP_PORT", str(port))
    elif caddy:
        env.set("APP_PORT", loopback_port(env))
    elif not needs_front(host) and (env.get("APP_PORT") or "").startswith("127.0.0.1:"):
        # Caddy is gone and people open the port itself again.
        env.set("APP_PORT", loopback_port(env).removeprefix("127.0.0.1:"))
    if env.get("DATA_CACHE_DEPLOYMENT") in {None, "", "development"}:
        env.set("DATA_CACHE_DEPLOYMENT", "production")
    env.set("SERVICES_ENABLED", "true" if choices.services else "false")
    if choices.services:
        # The names compose.yml's `name:` gives this project's network and
        # volume; the override sets the same pair for development.
        if env.is_unset("SERVICE_NETWORK"):
            env.set("SERVICE_NETWORK", "dataplayer_default")
        if env.is_unset("SERVICE_STORAGE_VOLUME"):
            env.set("SERVICE_STORAGE_VOLUME", "dataplayer_user-storage")


@dataclass
class Change:
    name: str
    before: str | None
    after: str | None


def changes(before: EnvFile, after: EnvFile) -> list[Change]:
    found = []
    for name in dict.fromkeys(before.names() + after.names()):
        old, new = before.get(name), after.get(name)
        if old != new:
            found.append(Change(name, old, new))
    return found


def warnings(changed: list[Change], existed: bool) -> list[str]:
    """What a change cannot do to a stack that has already been started."""
    if not existed:
        return []
    return [
        f"{change.name} is new, but {reason}: "
        "set it back if this stack was started before."
        for change in changed
        if (reason := FIXED_AT_FIRST_START.get(change.name)) and change.before is not None
    ]


# --- Questions ---------------------------------------------------------------


def ask_choice(prompt: str, options: tuple[str, ...], default: str, notes: dict[str, str]) -> str:
    print(bold(prompt))
    for number, option in enumerate(options, start=1):
        print(f"  {number}) {option:<9} {dim(notes.get(option, ''))}")
    default_number = options.index(default) + 1
    while True:
        answer = input(f"number [{default_number}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print(red(f"enter a number from 1 to {len(options)}."))


def ask_text(prompt: str, default: str) -> str:
    return input(f"{bold(prompt)} [{default}]: ").strip() or default


def ask_confirm(prompt: str, default_yes: bool = True) -> bool:
    hint = "Y/n" if default_yes else "y/N"
    while True:
        answer = input(f"{bold(prompt)} [{hint}]: ").strip().lower()
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


def ask_password() -> str | None:
    """A typed password, or nothing for a generated one."""
    choice = ask_choice(
        "superuser password",
        ("generate", "type"),
        "generate",
        {"generate": "shown once at the end, kept in .env", "type": "your own"},
    )
    if choice == "generate":
        return None
    while True:
        first = getpass.getpass("password: ")
        problem = password_problem(first)
        if problem is not None:
            print(red(problem))
        elif getpass.getpass("again: ") != first:
            print(red("the two do not match."))
        else:
            return first


def run_wizard(env: EnvFile, defaults: Choices) -> Choices:
    print()
    print(bold("DataPlayer setup") + dim("   Enter takes the value in brackets."))
    print()
    mode = ask_choice("what for", MODES, defaults.mode, MODE_HELP)
    if mode != defaults.mode and defaults.preset == default_preset(defaults.mode):
        defaults.preset = default_preset(mode)
    preset = ask_choice("preset", PRESETS, defaults.preset, PRESET_HELP)

    while True:
        email = ask_text("superuser email", env.get("FIRST_SUPERUSER") or "admin@example.com")
        if valid_email(email):
            break
        print(red("that does not look like an email address."))
    password = ask_password() if env.is_unset("FIRST_SUPERUSER_PASSWORD") else None

    host = None
    front = None
    services = False
    if mode == "prod":
        stored = env.get("FRONTEND_HOST")
        while True:
            host = ask_text(
                "address people open",
                stored if stored and not is_dev_origin(stored) else PROD_HOST,
            ).rstrip("/")
            if valid_host(host):
                break
            print(red("an address like http://localhost:8000 or https://data.example.com."))
        front = None
        if needs_front(host):
            front = ask_choice(
                "who serves HTTPS", FRONTS, defaults.front or "caddy", FRONT_HELP
            )
        print(dim("Managed services let the server start databases in containers of its own."))
        print(dim("Whatever reaches the container runtime reaches the whole host."))
        services = ask_confirm("allow managed services", default_yes=defaults.services)
    return Choices(
        mode, preset, services, email=email, password=password, host=host, front=front
    )


# --- Running -----------------------------------------------------------------


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write .env for DataPlayer.")
    parser.add_argument("--mode", choices=MODES, help="prod runs it, dev develops it.")
    parser.add_argument("--preset", choices=PRESETS)
    parser.add_argument("--superuser", metavar="EMAIL", help="the first superuser's email.")
    services = parser.add_mutually_exclusive_group()
    services.add_argument(
        "--enable-services",
        dest="services",
        action="store_true",
        default=None,
        help="let a running installation start containers (D82, D86).",
    )
    services.add_argument("--disable-services", dest="services", action="store_false")
    parser.add_argument(
        "--https",
        dest="front",
        choices=FRONTS,
        help="for an https:// address: caddy gets the certificate, own is a proxy of yours.",
    )
    parser.add_argument("--yes", action="store_true", help="ask nothing, write at once.")
    return parser.parse_args(argv)


def defaults_from(env: EnvFile | None, args: argparse.Namespace) -> Choices:
    """What the flags say, then what `.env` already says, then the defaults."""
    mode = args.mode or (env and current_mode(env)) or "prod"
    preset = args.preset or (env and current_preset(env)) or default_preset(mode)
    services = args.services if args.services is not None else bool(env and current_services(env))
    front = args.front or (env and current_front(env)) or None
    return Choices(mode, preset, services, email=args.superuser, front=front)


def describe(choices: Choices, changed: list[Change], notes: list[str]) -> None:
    profiles = ",".join(PROFILES[choices.preset]) or "none"
    print()
    print(bold("To be written to .env"))
    print(f"  mode {choices.mode}, preset {choices.preset} (profiles: {profiles})")
    generated = [c.name for c in changed if c.name in SECRETS]
    if generated:
        print("  " + green("secrets: ") + ", ".join(generated))
    for change in changed:
        if change.name not in SECRETS:
            print(f"  {change.name}: {dim(change.before or '-')} -> {change.after or dim('-')}")
    for note in notes:
        print("  " + yellow("note: ") + note)
    print()


def hand_over(path: Path, owner: Path) -> None:
    """Give a file written by root in a container to whoever owns the checkout."""
    if os.name == "nt" or os.geteuid() != 0:
        return
    stat = owner.stat()
    if stat.st_uid != 0:
        os.chown(path, stat.st_uid, stat.st_gid)


def write(path: Path, text: str) -> None:
    created = not path.exists()
    path.write_text(text, encoding="utf-8", newline="\n")
    if created:
        path.chmod(0o600)
    hand_over(path, path.parent)


def next_steps(choices: Choices, env: EnvFile, password_shown: bool) -> None:
    print(green(".env is written.") + " Start DataPlayer with:")
    print()
    print("  docker compose up -d --build")
    print()
    if choices.mode == "dev":
        print("then the interface: cd frontend && bun install && bun run dev")
        print("  http://localhost:5173, the API's docs at http://localhost:8000/docs")
        print(dim("examples for the connections panel: bun run seed:connectors"))
        print(dim("Adminer, Mailcatcher, a test Redis and SSH: docker compose --profile tools up -d"))
    else:
        host = env.get("FRONTEND_HOST") or ""
        print(f"then open {host}, sign in as {env.get('FIRST_SUPERUSER')}")
        for line in front_notes(host, current_front(env), env.get("APP_PORT") or "8000"):
            print(dim(line))
    if password_shown:
        print("password: " + bold(env.get("FIRST_SUPERUSER_PASSWORD") or "") + dim("  (also in .env)"))
    if choices.preset == "full":
        print(dim("The first start downloads the model search by meaning uses."))
    print(dim("Every docker compose command follows .env; run setup again to change it."))


def front_notes(host: str, front: str | None, port: str) -> list[str]:
    """What the machine must provide for the address to open."""
    name = urlsplit(host).hostname
    if front == "caddy":
        return [
            f"Caddy gets the certificate for {name} on the first start: the domain",
            "must point at this machine and ports 80 and 443 be open to the internet.",
            "Watch it with: docker compose logs -f caddy",
        ]
    if front == "own":
        return [
            f"Point your proxy at port {port.rsplit(':', 1)[-1]}, WebSockets included;",
            "docs/deployment.md has nginx and Traefik examples.",
        ]
    if name in LOCAL_HOSTS:
        return []
    return [
        "The port speaks plain HTTP: passwords typed into DataPlayer cross the",
        "network as text. docs/deployment.md says how to put HTTPS in front.",
    ]


def main(
    argv: list[str] | None = None,
    env_path: Path = ENV_PATH,
    frontend_env_path: Path = FRONTEND_ENV_PATH,
) -> int:
    args = parse_args(argv)
    existed = env_path.exists()
    before = EnvFile.load(env_path if existed else ENV_EXAMPLE_PATH)
    defaults = defaults_from(before if existed else None, args)

    interactive = sys.stdin.isatty() and not args.yes
    choices = run_wizard(before, defaults) if interactive else defaults
    password_generated = choices.password is None and before.is_unset("FIRST_SUPERUSER_PASSWORD")

    after = before.copy()
    configure(after, choices)
    changed = changes(before, after)
    notes = warnings(changed, existed)
    if not existed:
        notes.append(".env is created from .env.example.")
    if choices.mode == "dev" and not frontend_env_path.exists():
        notes.append("frontend/.env is created from frontend/.env.example.")
    describe(choices, changed, notes)

    if interactive and not ask_confirm("write it"):
        print("Nothing was written.")
        return 1
    write(env_path, after.render())
    if choices.mode == "dev" and not frontend_env_path.exists():
        write(frontend_env_path, FRONTEND_ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))
    # Shown on a terminal only, so a log of an unattended run never holds it.
    next_steps(choices, after, password_shown=password_generated and sys.stdout.isatty())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print()
        print("Nothing was written.")
        sys.exit(1)
