"""Connection and filesystem facts available without running remote commands."""

from dataclasses import dataclass
from typing import Any, Literal

import asyncssh

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.report_rows import page as report_page
from app.adapters.ssh import keys
from app.adapters.ssh.session import Remote, SshSession
from app.core.translation import N_, say

# A leading slash cannot be an SSH explorer node id: the explorer rejects it
# as an absolute path, so this virtual section cannot shadow a remote filename.
SECTION_ID = "/system"
SECTION_TITLE = N_("System")
SECTION_DESCRIPTION = N_("What this server says about itself")
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")

_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))


@dataclass(frozen=True)
class SystemReport:
    key: str
    title: str
    description: str
    kind: Literal["connection", "filesystem"]

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.key}"


REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        key="connection",
        title=N_("Connection"),
        description=N_(
            "Server identity, saved connection options and negotiated SSH and SFTP details"
        ),
        kind="connection",
    ),
    SystemReport(
        key="filesystem",
        title=N_("Filesystem"),
        description=N_(
            "Capacity of the folder's filesystem, when the SFTP server reports it"
        ),
        kind="filesystem",
    ),
)
_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(SECTION_ID + "/")


def report_for(node_id: str | None) -> SystemReport | None:
    return _BY_ID.get(node_id or "")


def section_node() -> ReportNode:
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: SystemReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=[_TABLE.model_copy(update={"title": say(_TABLE.title)})],
    )


class SshReports:
    def __init__(self, session: SshSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        report = report_for(request.node_id)
        if report is None:
            raise NodeNotFound(request.node_id)
        async with self._session.remote() as remote:
            if report.kind == "connection":
                rows = await self._connection_rows(remote)
            else:
                try:
                    rows = await self._filesystem_rows(remote)
                except AdapterError as failure:
                    if failure.error_kind != "unknown":
                        raise
                    rows = self._filesystem_unavailable()
        reason = say(
            '"{title}" is a report and holds no rows of its own',
            title=say(report.title),
        )
        return report_page(
            request,
            rows,
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
            read_only_reason=reason,
        )

    async def _connection_rows(self, remote: Remote) -> list[tuple[str, str]]:
        options = self._session.options
        facts = keys.host_key_facts(options.host_key)
        rows = [
            (say("Host"), options.host),
            (say("Port"), str(options.port)),
            (say("User"), options.username),
            (
                say("Authentication"),
                say("Key") if options.auth_method == "key" else say("Password"),
            ),
            (say("Folder"), remote.root),
            (say("Server key algorithm"), facts.algorithm),
            (say("Server key fingerprint"), facts.fingerprint),
            (say("SFTP version"), str(remote.sftp.version)),
            (say("Remote copy"), str(remote.sftp.supports_remote_copy).lower()),
        ]
        banner = _extra_info(remote, "server_version")
        if banner is not None:
            rows.append((say("Server banner"), banner))
        for key, label in (
            ("send_cipher", N_("Cipher (client to server)")),
            ("recv_cipher", N_("Cipher (server to client)")),
            ("send_mac", N_("MAC (client to server)")),
            ("recv_mac", N_("MAC (server to client)")),
            ("send_compression", N_("Compression (client to server)")),
            ("recv_compression", N_("Compression (server to client)")),
        ):
            value = _extra_info(remote, key)
            if value is not None:
                rows.append((say(label), value))
        return rows

    async def _filesystem_rows(self, remote: Remote) -> list[tuple[str, str]]:
        try:
            attrs = await remote.sftp.statvfs(remote.root)
        except asyncssh.SFTPError:
            return self._filesystem_unavailable()
        block_size = _number(attrs.frsize) or _number(attrs.bsize)
        if block_size <= 0:
            return self._filesystem_unavailable()
        return [
            (say("Filesystem block size bytes"), str(block_size)),
            (say("Filesystem total bytes"), str(block_size * attrs.blocks)),
            (say("Filesystem free bytes"), str(block_size * attrs.bfree)),
            (say("Filesystem available bytes"), str(block_size * attrs.bavail)),
            (say("Filesystem total inodes"), str(attrs.files)),
            (say("Filesystem free inodes"), str(attrs.ffree)),
            (say("Filesystem available inodes"), str(attrs.favail)),
        ]

    @staticmethod
    def _filesystem_unavailable() -> list[tuple[str, str]]:
        return [(say("Filesystem statistics"), say("Not reported through SFTP"))]


def _extra_info(remote: Remote, name: str) -> str | None:
    value = remote.connection.get_extra_info(name)
    return value if isinstance(value, str) and value != "" else None


def _number(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
