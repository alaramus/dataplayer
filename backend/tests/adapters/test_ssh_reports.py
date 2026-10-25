"""SSH reports use the authenticated protocol and never open a shell."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast

import asyncssh

from app.adapters.fetch import FetchRequest
from app.adapters.ssh import keys
from app.adapters.ssh.options import SshPassword
from app.adapters.ssh.reports import REPORTS, SshReports
from app.adapters.ssh.session import Remote, SshSession

_PINNED = keys.generate("ed25519", None).facts.public_key


class _Connection:
    def get_extra_info(self, name: str) -> object:
        return {
            "server_version": "SSH-2.0-OpenSSH_9.8",
            "send_cipher": "aes256-gcm@openssh.com",
            "recv_cipher": "aes256-gcm@openssh.com",
            "send_mac": "implicit",
            "recv_mac": "implicit",
            "send_compression": "none",
            "recv_compression": "none",
        }.get(name)


class _Sftp:
    version = 3
    supports_remote_copy = False

    async def statvfs(self, path: str) -> SimpleNamespace:
        assert path == "/srv/app"
        return SimpleNamespace(
            bsize=4096,
            frsize=1024,
            blocks=20,
            bfree=5,
            bavail=4,
            files=100,
            ffree=50,
            favail=40,
        )


class _Session:
    options = SshPassword(
        auth_method="password",
        host="example.org",
        port=2222,
        username="deploy",
        password="private-password",
        host_key=_PINNED,
    )

    def __init__(self) -> None:
        self.remote_value = Remote(
            sftp=cast(asyncssh.SFTPClient, _Sftp()),
            root="/srv/app",
            connection=cast(asyncssh.SSHClientConnection, _Connection()),
        )

    @asynccontextmanager
    async def remote(self) -> AsyncIterator[Remote]:
        yield self.remote_value


def _reports(session: _Session) -> SshReports:
    return SshReports(cast(SshSession, session))


async def test_connection_report_shows_public_protocol_facts_but_no_credentials() -> None:
    page = await _reports(_Session()).fetch(FetchRequest(node_id=REPORTS[0].node_id))
    rows = dict(page.rows)

    assert rows["Host"] == "example.org"
    assert rows["Folder"] == "/srv/app"
    assert rows["Server banner"] == "SSH-2.0-OpenSSH_9.8"
    assert rows["Server key algorithm"] == "ssh-ed25519"
    assert rows["Cipher (client to server)"] == "aes256-gcm@openssh.com"
    assert all("private-password" not in value for value in rows.values())
    assert page.record_supported is False
    assert page.update_supported is False
    assert page.page_commands == ["share"]


async def test_filesystem_report_uses_sftp_capacity_and_inode_counts() -> None:
    page = await _reports(_Session()).fetch(FetchRequest(node_id=REPORTS[1].node_id))
    rows = dict(page.rows)

    assert rows["Filesystem total bytes"] == "20480"
    assert rows["Filesystem free bytes"] == "5120"
    assert rows["Filesystem available bytes"] == "4096"
    assert rows["Filesystem total inodes"] == "100"
    assert rows["Filesystem available inodes"] == "40"
