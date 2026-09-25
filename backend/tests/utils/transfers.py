"""A transfer carried out without a job, for the kinds that move bytes (D168)."""

import uuid
from collections.abc import Awaitable, Callable

from app.adapters.protocol import DataAdapter
from app.connectors.paste.kinds import PastesAsJob
from app.connectors.paste.models import PasteRun
from app.connectors.paste.transfer import Transfer, in_worker


class Recorder:
    """A report that keeps what it was told, and can act on the way."""

    def __init__(
        self,
        *,
        on_progress: Callable[[Transfer], Awaitable[None]] | None = None,
    ) -> None:
        self.transfer: Transfer | None = None
        self.progress = 0
        self.removing_seen = False
        self._on_progress = on_progress

    async def in_thread[T](self, work: Callable[[], T]) -> T:
        return await in_worker(work)

    async def progressed(self) -> None:
        self.progress += 1
        if self._on_progress is not None and self.transfer is not None:
            await self._on_progress(self.transfer)

    async def removing(self) -> None:
        self.removing_seen = True


async def planned(
    kind: PastesAsJob, source: DataAdapter, destination: DataAdapter, request: PasteRun
) -> Transfer:
    """The payload the paste route would write for this request."""
    plan = await kind.plan(source, destination, request)
    return Transfer(
        kind=kind.name,
        title=kind.title,
        doing=kind.doing,
        done=kind.done,
        mode=kind.mode,
        conflict=request.conflict,
        source_connector_id=request.source_connector_id,
        source_label="Left",
        destination_connector_id=uuid.uuid4(),
        destination_node_id=request.destination_node_id,
        destination_label="Right",
        place_label=plan.place or "Right",
        name=plan.name,
        items=plan.items,
        bytes_total=plan.bytes_total,
    )


async def transferred(
    kind: PastesAsJob,
    source: DataAdapter,
    destination: DataAdapter,
    request: PasteRun,
    report: Recorder | None = None,
) -> Transfer:
    """Plan it, then carry it out; the payload says how each item ended."""
    transfer = await planned(kind, source, destination, request)
    recorder = report or Recorder()
    recorder.transfer = transfer
    await kind.transfer(source, destination, transfer, recorder)
    return transfer
