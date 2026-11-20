"""An FTP server as a source: the file explorer over its files (D150, D384).

Everything the file source does is the explorer's and comes with it; what is
here is the server: how it is reached, which actions it offers and its
address (D386).
"""

from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import quote, unquote, urlsplit

from app.adapters.explorer.actions import (
    EXPLORER_ACTION_TYPES,
    ConnectFolder,
    ExplorerActionType,
)
from app.adapters.explorer.explorer import Explorer
from app.adapters.ftp.options import (
    ANONYMOUS_USER,
    DEFAULT_PORT,
    IMPLICIT_PORT,
    FtpOptions,
)
from app.adapters.ftp.storage import FtpStorage
from app.adapters.registry import AdapterContext, register
from app.core.translation import N_, say


class FtpAdapter(Explorer):
    """The explorer over one folder of an FTP server."""

    # A folder of a server does not become a connection of its own: the draft
    # would carry this connection's password to the browser, as SSH's would.
    explorer_action_types: ClassVar[tuple[ExplorerActionType, ...]] = tuple(
        action_type
        for action_type in EXPLORER_ACTION_TYPES
        if action_type is not ConnectFolder
    )

    def __init__(self, options: FtpOptions, context: AdapterContext) -> None:
        self._options = options
        super().__init__(FtpStorage(options))

    def connection_string(self) -> str:
        value = self.draft_connection_string(self._options.model_dump(mode="python"))
        if value is None:  # pragma: no cover - validated options always have a host
            raise ValueError(say("The FTP connection has no host"))
        return value

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        """`ftp://user@host:port/folder`, never with the password (D386).

        `ftps://` is implicit TLS, as curl and every client read it; explicit
        TLS is `ftp://`, since it begins as plain FTP on the same port.
        """
        host = options.get("host")
        if not isinstance(host, str) or host.strip() == "":
            return None
        host = host.strip()
        implicit = options.get("security") == "implicit"
        address = f"[{host}]" if ":" in host else host
        user = options.get("username")
        if options.get("auth_method") != "anonymous" and isinstance(user, str) and user:
            address = f"{quote(user, safe='')}@{address}"
        port = options.get("port")
        default = IMPLICIT_PORT if implicit else DEFAULT_PORT
        if isinstance(port, int) and not isinstance(port, bool) and port != default:
            address = f"{address}:{port}"
        folder = options.get("path")
        path = ""
        if isinstance(folder, str) and folder not in ("", "/"):
            path = "/" + quote(folder.lstrip("/"), safe="/")
            # An absolute folder is `//` after the host, as RFC 1738 spells it.
            if folder.startswith("/"):
                path = "/" + path
        return f"{'ftps' if implicit else 'ftp'}://{address}{path}"

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        """The server, the port, the user and the folder an address names.

        Every part is answered, an empty one as empty, so a part erased from
        the box is erased from the form. A password in it is refused, as it
        would otherwise sit in the address in the clear.
        """
        try:
            parts = urlsplit(url.strip())
            port = parts.port
        except ValueError:
            raise ValueError(say("That is not an FTP address")) from None
        if (
            parts.scheme not in ("ftp", "ftps")
            or not parts.hostname
            or parts.password is not None
            or parts.query != ""
            or parts.fragment != ""
        ):
            raise ValueError(say("That is not an FTP address"))
        implicit = parts.scheme == "ftps"
        path = unquote(parts.path)
        folder = "/" + path[2:].strip("/") if path.startswith("//") else path.strip("/")
        user = unquote(parts.username) if parts.username is not None else ""
        found: dict[str, Any] = {
            "host": parts.hostname,
            "port": port or (IMPLICIT_PORT if implicit else DEFAULT_PORT),
            "path": folder,
        }
        if implicit:
            found["security"] = "implicit"
        if user and user != ANONYMOUS_USER:
            found["username"] = user
        return found


@register(
    name="ftp",
    title=N_("FTP"),
    category="files",
    description=N_(
        "A server reached over FTP or FTPS. Browse its folders from where you "
        "choose and work with its files as with your own: tables, SQL over "
        "files, the editor, archives, search and copying between connections. "
        "Signs in with a password or anonymously."
    ),
    options_schema=FtpOptions,
    adapter_class=FtpAdapter,
)
def _build(options: FtpOptions, context: AdapterContext) -> FtpAdapter:
    return FtpAdapter(options, context)
