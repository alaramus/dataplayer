import socket
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def silent_endpoint() -> Iterator[int]:
    """A port that accepts the connection and then says nothing.

    A closed port cannot stand in for an unreachable server: Linux refuses it
    at once and Windows leaves the client waiting, so a test written against
    one of them asserts about the platform rather than about the adapter. This
    listens without ever accepting, so the kernel completes the handshake from
    the backlog and the client waits for a greeting that never comes — the same
    everywhere, and the timeout budget is what ends it.
    """
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port: int = server.getsockname()[1]
        yield port
    finally:
        server.close()
