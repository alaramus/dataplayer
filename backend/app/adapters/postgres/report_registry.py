"""Resolve discovered reports identically for every read surface (D121)."""

from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import SystemReport, report_for
from app.adapters.postgres.timescale.profile import discover
from app.adapters.postgres.timescale.report_access import require_report
from app.adapters.postgres.timescale.reports import BY_ID, TIMESCALE_SECTION_ID
from app.adapters.protocol import NodeNotFound
from app.core.translation import say


async def require_timescale(session: PostgresSession) -> None:
    profile = await discover(session)
    if profile.feature.state == "absent":
        raise NodeNotFound(TIMESCALE_SECTION_ID)
    if not profile.available:
        raise ValueError(profile.feature.reason or say("TimescaleDB inspection is unavailable"))


async def resolve_report(
    session: PostgresSession, node_id: str
) -> SystemReport | None:
    report = report_for(node_id)
    if report is not None:
        return report
    if node_id == TIMESCALE_SECTION_ID or node_id.startswith(
        f"{TIMESCALE_SECTION_ID}."
    ):
        report = BY_ID.get(node_id)
        if report is None:
            raise NodeNotFound(node_id)
        await require_timescale(session)
        await require_report(session, report)
        return report
    return None
