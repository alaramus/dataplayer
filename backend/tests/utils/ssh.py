"""The development SSH server's own key, asked for once per run.

OpenSSH counts every connection that leaves before signing in, and fetching a
server's key is exactly that. One fetch per test was enough for the server to
refuse this machine for a while (`PerSourcePenalties`, OpenSSH 9.8 and later),
and every test after it failed on a closed door. The tests of fetching itself
still fetch; everything else asks here.
"""

from app.adapters.ssh.adapter import SshAdapter

_known: dict[tuple[str, int], str] = {}


async def pinned_key(host: str, port: int) -> str:
    """The key the server presents, as a connection would pin it (D145)."""
    if (host, port) not in _known:
        described = await SshAdapter.presented_server_key({"host": host, "port": port})
        _known[(host, port)] = described.public_key
    return _known[(host, port)]
