"""Files and folders copied or moved between connections (D161, D163, D168, D169)."""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Protocol, runtime_checkable

from anyio import to_thread

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import (
    Entry,
    Place,
    Storage,
    VersionChanged,
    is_plain_name,
    node_id_of,
)
from app.adapters.protocol import AdapterError, DataAdapter
from app.connectors.paste.kinds import offered, refused
from app.connectors.paste.models import (
    Availability,
    ClipboardMode,
    Conflict,
    Foreseen,
    PairEnd,
    PasteColumn,
    PasteKindName,
    PasteOffer,
    PastePair,
    PasteRun,
    PasteWorkflow,
)
from app.connectors.paste.transfer import (
    PIECE_BYTES,
    Transfer,
    TransferItem,
    TransferOutcome,
    TransferPlan,
    TransferReport,
    TransferStopped,
)
from app.core.access import Access
from app.core.translation import N_, say

# The ceiling D74 holds for a folder copied within one connection, and D168's.
MAX_TRANSFER_ENTRIES = 10_000
MAX_TRANSFER_BYTES = 10 * 1024 * 1024 * 1024
TOO_MANY = N_("That is more than 10,000 files and folders")
TOO_LARGE = N_("The selection exceeds 10 GB")


@runtime_checkable
class TransfersFiles(Protocol):
    @property
    def storage(self) -> Storage: ...


@runtime_checkable
class OnThisDisk(Protocol):
    """A storage whose places are paths on this machine, which can be compared."""

    def path_of(self, place: Place) -> Path: ...


def storage_of(adapter: DataAdapter) -> Storage:
    if not isinstance(adapter, TransfersFiles):
        raise ActionRefused("not_applicable", say("This connection does not hold files"))
    return adapter.storage


def destination_folder(storage: Storage, folder_id: str | None) -> Place:
    place = storage.place(folder_id)
    found = storage.entry(place)
    if found is None or not found.is_directory:
        raise ActionRefused("not_applicable", say("Choose a destination folder"))
    return place


def free_place(storage: Storage, folder: Place, name: str) -> Place:
    """Keep both: the first `name (n)` nothing holds."""
    stem, dot, suffix = name.rpartition(".")
    if not dot or not stem:
        stem, suffix = name, ""
    for number in range(1, 10_001):
        candidate = storage.child(
            folder, f"{stem} ({number}){'.' + suffix if suffix else ''}"
        )
        if storage.entry(candidate) is None:
            return candidate
    raise ActionRefused("conflict", say("No free name is available"))


def place_for(storage: Storage, folder: Place, name: str, conflict: Conflict) -> Place:
    """Where a file of this name lands under a conflict rule, or why it cannot."""
    target = storage.child(folder, name)
    existing = storage.entry(target)
    if existing is None:
        return target
    if existing.is_directory:
        raise ActionRefused("not_applicable", say("{name} is a folder here", name=name))
    if conflict == "refuse":
        raise ActionRefused("conflict", say("{name} is already there", name=name))
    if conflict == "replace":
        return target
    return free_place(storage, folder, name)


def folder_place_for(
    storage: Storage, folder: Place, name: str, conflict: Conflict
) -> Place:
    """Where a folder lands. Never Replace: the old folder would go before the
    new one had arrived, and a Stop halfway would leave neither (D169)."""
    target = storage.child(folder, name)
    if storage.entry(target) is None:
        return target
    if conflict == "refuse":
        raise ActionRefused("conflict", say("{name} is already there", name=name))
    if conflict == "replace":
        raise ActionRefused(
            "not_applicable",
            say("{name} is a folder, which is kept rather than replaced", name=name),
        )
    return free_place(storage, folder, name)


def source_files(source: Storage, node_ids: list[str]) -> list[Entry]:
    """What was ticked, or why it cannot leave this connection.

    No walk: this answers every change of a tick. The folders are counted when
    Paste is chosen.
    """
    if len(set(node_ids)) != len(node_ids):
        raise ActionRefused("not_applicable", say("The selection contains a file twice"))
    entries: list[Entry] = []
    names: set[str] = set()
    total = 0
    for node_id in node_ids:
        entry = source.entry(source.place(node_id))
        if entry is None:
            raise ActionRefused("not_applicable", say("A copied file no longer exists"))
        if entry.is_link:
            # Resolved, a link would carry the tree it points at (D169).
            raise ActionRefused("not_applicable", say("Copy files and folders, not links"))
        if not is_plain_name(entry.name):
            raise ActionRefused("not_applicable", say("A file has an invalid name"))
        if entry.name in names:
            raise ActionRefused("not_applicable", say("Two files have the same name"))
        if not entry.is_directory:
            total += entry.size_bytes
            if total > MAX_TRANSFER_BYTES:
                raise ActionRefused("not_applicable", say(TOO_LARGE))
        names.add(entry.name)
        entries.append(entry)
    return entries


@dataclass(frozen=True)
class Checked:
    entries: list[Entry]
    folder: Place
    # Whether Replace is on offer: not when a taken name is a folder's.
    replaceable: bool


def checked_files(
    source: Storage,
    destination: Storage,
    node_ids: list[str],
    folder_id: str | None,
    conflict: Conflict,
) -> Checked:
    """What was ticked and where it goes, or why not, without opening a byte."""
    entries = source_files(source, node_ids)
    folder = destination_folder(destination, folder_id)
    replaceable = True
    taken: str | None = None
    for entry in entries:
        existing = destination.entry(destination.child(folder, entry.name))
        if existing is None:
            continue
        taken = taken or entry.name
        if entry.is_directory or existing.is_directory:
            replaceable = False
    if taken is not None and conflict == "refuse":
        raise ActionRefused("conflict", say("{name} is already there", name=taken))
    for entry in entries:
        if entry.is_directory:
            folder_place_for(destination, folder, entry.name, conflict)
        else:
            place_for(destination, folder, entry.name, conflict)
    return Checked(entries=entries, folder=folder, replaceable=replaceable)


def inspect_files(
    source: Storage,
    destination: Storage,
    node_ids: list[str],
    folder_id: str | None,
    conflict: Conflict = "refuse",
) -> tuple[ActionRefused | None, bool]:
    """Why the selection cannot be pasted now, and whether Replace may be offered."""
    try:
        checked = checked_files(source, destination, node_ids, folder_id, conflict)
    except ActionRefused as refusal:
        return refusal, _replaceable(source, destination, node_ids, folder_id)
    except (OSError, ValueError):
        return ActionRefused("not_applicable", say("A source or destination is unavailable")), True
    return None, checked.replaceable


def _replaceable(
    source: Storage, destination: Storage, node_ids: list[str], folder_id: str | None
) -> bool:
    try:
        return checked_files(source, destination, node_ids, folder_id, "rename").replaceable
    except (ActionRefused, OSError, ValueError):
        return True


def walk(
    storage: Storage, place: Place, below: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], Entry]]:
    """Every entry below a folder with its path below it, parents first; a
    link is yielded and never followed."""
    for entry in storage.entries(place):
        path = (*below, entry.name)
        yield path, entry
        if entry.is_directory and not entry.is_link:
            yield from walk(storage, entry.place, path)


def _measured(source: Storage, entries: list[Entry]) -> tuple[list[TransferItem], int]:
    """Each ticked item with its files and bytes, within the ceilings.

    The walk stops as soon as a ceiling is crossed, so a refusal is quick.
    """
    items: list[TransferItem] = []
    counted = 0
    total = 0
    for entry in entries:
        counted += 1
        if not entry.is_directory:
            total += entry.size_bytes
            items.append(
                TransferItem(node_id=entry.place.key, name=entry.name, size_bytes=entry.size_bytes)
            )
        else:
            files = 0
            size = 0
            for _path, below in walk(source, entry.place):
                counted += 1
                if counted > MAX_TRANSFER_ENTRIES:
                    raise ActionRefused("too_large", say(TOO_MANY))
                if not below.is_directory and not below.is_link:
                    files += 1
                    size += below.size_bytes
                    if total + size > MAX_TRANSFER_BYTES:
                        raise ActionRefused("too_large", TOO_LARGE)
            total += size
            items.append(
                TransferItem(
                    node_id=entry.place.key,
                    name=entry.name,
                    is_folder=True,
                    size_bytes=size,
                    files=files,
                )
            )
        if counted > MAX_TRANSFER_ENTRIES:
            raise ActionRefused("too_large", say(TOO_MANY))
        if total > MAX_TRANSFER_BYTES:
            raise ActionRefused("too_large", TOO_LARGE)
    return items, total


def taken_there(
    destination: Storage, folder_id: str | None, name: str, is_folder: bool
) -> tuple[ActionRefused | None, bool]:
    """Whether one name is taken in a folder, and whether Replace may be offered.

    What a pipeline asks of a file a link has yet to make (D178): its name is
    known, and nothing else about it is.
    """
    try:
        folder = destination_folder(destination, folder_id)
        existing = destination.entry(destination.child(folder, name))
    except ActionRefused as refusal:
        return refusal, True
    except (OSError, ValueError):
        return ActionRefused("not_applicable", say("A source or destination is unavailable")), True
    if existing is None:
        return None, True
    replaceable = not (is_folder or existing.is_directory)
    return ActionRefused("conflict", say("{name} is already there", name=name)), replaceable


def _into_itself(source: Storage, destination: Storage, checked: Checked) -> None:
    """A folder pasted into its own subtree would be read while it is written.

    Two file connections can open one personal folder at different depths;
    where both ends are on this machine, the real paths say so (D169).
    """
    if not isinstance(source, OnThisDisk) or not isinstance(destination, OnThisDisk):
        return
    into = destination.path_of(checked.folder).resolve()
    for entry in checked.entries:
        if not entry.is_directory:
            continue
        folder = source.path_of(entry.place).resolve()
        if into == folder or folder in into.parents:
            raise ActionRefused(
                "not_applicable", say("{name} cannot be put inside itself", name=entry.name)
            )


def _planned(source: Storage, destination: Storage, request: PasteRun) -> TransferPlan:
    try:
        checked = checked_files(
            source,
            destination,
            request.source_node_ids,
            request.destination_node_id,
            request.conflict,
        )
        _into_itself(source, destination, checked)
        items, total = _measured(source, checked.entries)
    except (OSError, ValueError):
        raise ActionRefused(
            "not_applicable", say("A source or destination is unavailable")
        ) from None
    # The ids as they were sent, which is how the job asks for them again.
    for item, node_id in zip(items, request.source_node_ids, strict=True):
        item.node_id = node_id
    return TransferPlan(items=items, bytes_total=total, place=checked.folder.name)


class _Failed(Exception):
    """This file did not arrive; the next one may."""


@dataclass
class _Arrival:
    item: TransferItem
    place: Place
    version: str
    path: str


@dataclass
class _Run:
    """One transfer as it is carried out: where the bytes stand, and what a
    move removes at the end."""

    source: Storage
    destination: Storage
    transfer: Transfer
    report: TransferReport
    settled: int = 0
    arrivals: list[_Arrival] = field(default_factory=list)
    folders: list[Place] = field(default_factory=list)

    async def file(self, item: TransferItem, folder: Place) -> None:
        async def carry() -> None:
            place = await self.report.in_thread(partial(self.source.place, item.node_id))
            entry = await self.report.in_thread(partial(self.source.entry, place))
            if entry is None:
                raise _Failed(say("{name} no longer exists", name=item.name))
            if entry.is_directory or entry.is_link:
                raise _Failed(say("{name} is no longer a file", name=item.name))
            target = await self.report.in_thread(
                partial(place_for, self.destination, folder, entry.name, self.transfer.conflict)
            )
            self.transfer.current = item.name
            version = await self._carry(
                place, entry.size_bytes, target, replace=self.transfer.conflict == "replace"
            )
            item.arrived = 1
            if target.name != item.name:
                item.published_as = target.name
            item.published_id = node_id_of(target)
            self.arrivals.append(_Arrival(item, place, version, item.name))

        failure = await self._attempt(carry, item.name)
        if failure is not None:
            item.failed = 1
            item.message = failure
        self._settle(item.size_bytes or 0)

    async def folder(self, item: TransferItem, folder: Place) -> None:
        place = await self.report.in_thread(partial(self.source.place, item.node_id))
        top = await self.report.in_thread(partial(self.source.entry, place))
        if top is None or not top.is_directory or top.is_link:
            item.failed = item.files or 1
            item.message = say("{name} is no longer a folder", name=item.name)
            return
        try:
            target = await self.report.in_thread(
                partial(
                    folder_place_for, self.destination, folder, top.name, self.transfer.conflict
                )
            )
            await self.report.in_thread(partial(self.destination.make_directory, target))
        except ActionRefused as refusal:
            item.failed = item.files or 1
            item.message = refusal.message
            return
        except FileExistsError:
            item.failed = item.files or 1
            item.message = say("{name} is already there", name=item.name)
            return
        self.transfer.published += 1
        if target.name != item.name:
            item.published_as = target.name
        item.published_id = node_id_of(target)
        self.folders.append(place)
        tree = await self.report.in_thread(lambda: list(walk(self.source, place)))
        made: dict[tuple[str, ...], Place] = {(): target}
        for below, entry in tree:
            parent = made.get(below[:-1])
            if parent is None:
                # Its folder could not be made; that failure is counted there.
                continue
            path = "/".join((item.name, *below))
            if entry.is_link:
                item.skipped += 1
                self.transfer.problem(path, say("{path} is a link and was skipped", path=path))
                continue
            if entry.is_directory:
                made_here = await self._made(parent, entry.name, path)
                if made_here is None:
                    item.failed += 1
                else:
                    made[below] = made_here
                    self.folders.append(entry.place)
                continue
            failure = await self._attempt(
                partial(self._below, item, entry, parent, path), path
            )
            if failure is not None:
                item.failed += 1
                self.transfer.problem(path, failure)
            self._settle(entry.size_bytes)
            await self.report.progressed()

    async def _below(self, item: TransferItem, entry: Entry, parent: Place, path: str) -> None:
        target = await self.report.in_thread(
            partial(self.destination.child, parent, entry.name)
        )
        self.transfer.current = path
        version = await self._carry(entry.place, entry.size_bytes, target, replace=False)
        item.arrived += 1
        self.arrivals.append(_Arrival(item, entry.place, version, path))

    async def _made(self, parent: Place, name: str, path: str) -> Place | None:
        try:
            child = await self.report.in_thread(partial(self.destination.child, parent, name))
            await self.report.in_thread(partial(self.destination.make_directory, child))
        except (OSError, ValueError, ActionRefused):
            self.transfer.problem(
                path, say("{path} could not be created, nor anything in it", path=path)
            )
            return None
        self.transfer.published += 1
        return child

    async def _attempt(self, carry: Callable[[], Awaitable[None]], name: str) -> str | None:
        """Carry one file; its failure in a sentence, or None when it arrived.

        What no later file could survive — a connection gone, the destination
        folder gone — ends the transfer instead.
        """
        try:
            await carry()
        except _Failed as failure:
            return str(failure)
        except ActionRefused as refusal:
            return refusal.message
        except VersionChanged:
            return say("{name} changed while it was being copied", name=name)
        except ValueError:
            return say("{name} cannot be named there", name=name)
        except AdapterError as failure:
            raise TransferStopped(failure.message) from None
        except FileExistsError:
            return say("{name} is already there", name=name)
        except OSError:
            # One file, or everything after it? The folder answers.
            await _folder(self.report, self.destination, self.transfer.destination_node_id)
            return say("{name} could not be copied", name=name)
        return None

    async def _carry(self, place: Place, size: int, target: Place, *, replace: bool) -> str:
        """The bytes of one file, piece by piece; the version read, once it is
        in place whole."""
        report = self.report
        version = await report.in_thread(partial(self.source.version, place))
        changed = _Failed(
            say("{name} changed while it was being copied", name=self.transfer.current)
        )
        stack = ExitStack()
        try:
            arriving = await report.in_thread(
                partial(stack.enter_context, self.destination.incoming(target))
            )
            readable = await report.in_thread(partial(self.source.open, place))
            stack.callback(readable.close)
            written = 0
            while chunk := await report.in_thread(partial(readable.read, PIECE_BYTES)):
                written += len(chunk)
                if written > size:
                    raise changed
                await report.in_thread(partial(arriving.write, chunk))
                self.transfer.bytes_done = self.settled + written
                await report.progressed()
            if written != size:
                raise changed
            if await report.in_thread(partial(self.source.version, place)) != version:
                raise changed
            await report.in_thread(partial(arriving.publish, target, replace=replace))
        finally:
            await report.in_thread(stack.close)
        self.transfer.published += 1
        return version

    def _settle(self, size: int) -> None:
        self.settled += size
        self.transfer.bytes_done = self.settled
        self.transfer.files_done += 1

    async def let_go(self) -> None:
        """A move removes its sources only now that everything was copied:
        each file still as it was read, then each folder left empty (D169)."""
        report = self.report
        for arrival in self.arrivals:
            try:
                now = await report.in_thread(partial(self.source.version, arrival.place))
                if now != arrival.version:
                    self._kept(
                        arrival,
                        N_("{path} was copied, but its source changed after it was read and was kept"),
                    )
                    continue
                await report.in_thread(partial(self.source.remove, arrival.place))
            except (OSError, AdapterError):
                self._kept(arrival, N_("{path} was copied, but its source could not be removed"))
                continue
            arrival.item.removed += 1
            await report.progressed()
        # Parents were listed before their children, so the deepest go first.
        for place in reversed(self.folders):
            try:
                await report.in_thread(partial(self.source.remove_empty, place))
            except (OSError, AdapterError):
                # Still holding something: a file that failed, a link, a
                # file somebody added meanwhile.
                continue

    def _kept(self, arrival: _Arrival, said: str) -> None:
        sentence = say(said, path=arrival.path)
        if arrival.item.is_folder:
            self.transfer.problem(arrival.path, sentence)
        else:
            arrival.item.message = sentence


def _copied(item: TransferItem) -> TransferOutcome:
    return "failed" if item.failed else "done"


def _moved(item: TransferItem) -> TransferOutcome:
    if item.outcome == "stopped":
        return "stopped"
    if item.failed:
        return "failed"
    return "kept" if item.removed < item.arrived else "done"


class _Files:
    name: PasteKindName
    title: str
    needs: str
    doing: str
    done: str
    mode: ClipboardMode
    can_replace: bool
    source_requires: Access
    changes_source: bool
    converts = False
    workflow: PasteWorkflow = "run"
    destination_requires: Access = "write"
    makes = True
    pipelines = True
    outranks: tuple[PasteKindName, ...] = ()

    def takes_from(self, source: DataAdapter) -> bool:
        return isinstance(source, TransfersFiles)

    def serves(self, source: DataAdapter, destination: DataAdapter) -> bool:
        return isinstance(source, TransfersFiles) and isinstance(
            destination, TransfersFiles
        )

    async def supply(self, source: DataAdapter, node_ids: list[str]) -> Availability:
        try:
            await to_thread.run_sync(source_files, storage_of(source), node_ids)
        except ActionRefused as refusal:
            return Availability(available=False, reason=refusal.message)
        except (OSError, ValueError):
            return Availability(available=False, reason=say("The selection is unavailable"))
        return Availability(available=True)

    async def offer(
        self, source: DataAdapter, destination: DataAdapter, pair: PastePair
    ) -> PasteOffer:
        problem, replaceable = await to_thread.run_sync(
            inspect_files,
            storage_of(source),
            storage_of(destination),
            pair.source_node_ids,
            pair.destination_node_id,
        )
        can_replace = self.can_replace and replaceable
        if problem is None:
            return offered(self, available=True, can_replace=can_replace)
        return offered(
            self,
            available=False,
            reason=problem.message,
            name_conflict=problem.reason == "conflict",
            can_replace=can_replace,
        )

    def made(
        self, source: Foreseen, name: str | None, columns: list[PasteColumn] | None
    ) -> Foreseen | None:
        del name, columns  # a file keeps its own name, and its columns with it
        return None if source.kind == "table" else source

    async def foresee(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        source_end: PairEnd,
        target_end: PairEnd,
    ) -> PasteOffer:
        if isinstance(source_end, Foreseen):
            if source_end.kind == "table":
                return refused(self, self.needs)
            if not is_plain_name(source_end.name):
                return refused(self, say("A file has an invalid name"))
            name, is_folder = source_end.name, source_end.kind == "folder"
        elif source_end is None:
            return refused(self, self.needs)
        else:
            try:
                entries = await to_thread.run_sync(
                    source_files, storage_of(source), [source_end]
                )
            except ActionRefused as refusal:
                return refused(self, refusal.message)
            except (OSError, ValueError):
                return refused(self, say("The selection is unavailable"))
            name, is_folder = entries[0].name, entries[0].is_directory
        can_replace = self.can_replace and not is_folder
        if isinstance(target_end, Foreseen):
            if target_end.kind != "folder":
                return refused(self, say("Choose a destination folder"))
            # A folder a link has yet to make holds no name to be taken.
            return offered(self, available=True, can_replace=can_replace)
        problem, replaceable = await to_thread.run_sync(
            taken_there, storage_of(destination), target_end, name, is_folder
        )
        can_replace = can_replace and replaceable
        if problem is None:
            return offered(self, available=True, can_replace=can_replace)
        return offered(
            self,
            available=False,
            reason=problem.message,
            name_conflict=problem.reason == "conflict",
            can_replace=can_replace,
        )

    async def plan(
        self, source: DataAdapter, destination: DataAdapter, request: PasteRun
    ) -> TransferPlan:
        if request.conflict == "replace" and not self.can_replace:
            raise ActionRefused(
                "not_applicable", say("A move between connections cannot replace a file")
            )
        return await to_thread.run_sync(
            _planned, storage_of(source), storage_of(destination), request
        )

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        """Everything is copied first; a move removes its sources at the end."""
        run = _Run(storage_of(source), storage_of(destination), transfer, report)
        folder = await _folder(report, run.destination, transfer.destination_node_id)
        for item in transfer.items:
            item.outcome = "running"
            await report.progressed()
            try:
                if item.is_folder:
                    await run.folder(item, folder)
                else:
                    await run.file(item, folder)
            except asyncio.CancelledError:
                item.outcome = "stopped"
                item.message = (
                    say("{name} was stopped partway; what arrived stays", name=item.name)
                    if item.is_folder
                    else say(
                        "{name} was stopped while it was being copied; "
                        "nothing is left under its name",
                        name=item.name,
                    )
                )
                raise
            except TransferStopped:
                item.outcome = "failed" if item.arrived or item.failed else "pending"
                raise
            item.outcome = _copied(item)
            await report.progressed()
        transfer.current = None
        if not self.changes_source:
            return
        await report.removing()
        try:
            await run.let_go()
        finally:
            for item in transfer.items:
                item.outcome = _moved(item)

    def told(self, transfer: Transfer, stopped: str | None = None) -> str:
        return told_files(transfer, stopped)


async def _folder(report: TransferReport, storage: Storage, folder_id: str | None) -> Place:
    """The destination folder, or the end of the transfer."""
    try:
        return await report.in_thread(partial(destination_folder, storage, folder_id))
    except ActionRefused:
        raise TransferStopped(say("The destination folder is no longer there")) from None
    except AdapterError as failure:
        raise TransferStopped(failure.message) from None
    except (OSError, ValueError):
        raise TransferStopped(say("The destination folder could not be reached")) from None


# Whole sentences for each mode and each count, since a verb and a plural are
# words rather than values (D226). Keyed by mode and by whether one was counted.
_ALL_FILES = {
    ("copy", True): N_("Copied {count} file to {place}"),
    ("copy", False): N_("Copied {count} files to {place}"),
    ("move", True): N_("Moved {count} file to {place}"),
    ("move", False): N_("Moved {count} files to {place}"),
}
_ALL_ITEMS = {
    ("copy", True): N_("Copied {count} item to {place}"),
    ("copy", False): N_("Copied {count} items to {place}"),
    ("move", True): N_("Moved {count} item to {place}"),
    ("move", False): N_("Moved {count} items to {place}"),
}
_SOME_FILES = {
    ("copy", True): N_("Copied {done} of {count} file to {place}"),
    ("copy", False): N_("Copied {done} of {count} files to {place}"),
    ("move", True): N_("Moved {done} of {count} file to {place}"),
    ("move", False): N_("Moved {done} of {count} files to {place}"),
}
_LINKS_SKIPPED = {
    True: N_("{count} link skipped"),
    False: N_("{count} links skipped"),
}


def told_files(transfer: Transfer, stopped: str | None = None) -> str:
    """"Copied 4,208 of 4,211 files to reports; 3 failed, 1 link skipped"."""
    items = transfer.items
    total = transfer.files_total
    arrived = sum(item.arrived for item in items)
    failed = sum(item.failed for item in items)
    skipped = sum(item.skipped for item in items)
    moving = transfer.mode == "move"
    done = sum(item.removed for item in items) if moving else arrived
    kept = arrived - done if moving else 0
    halted = any(item.outcome == "stopped" for item in items)
    missing = max(total - arrived - failed, 0)
    mode = transfer.mode
    place = transfer.place_label
    links = (
        say(_LINKS_SKIPPED[skipped == 1], count=f"{skipped:,}") if skipped else None
    )
    if done == total and not (failed or kept or missing or halted or stopped):
        whole = (
            say(_ALL_FILES[mode, total == 1], count=f"{total:,}", place=place)
            if total
            else say(_ALL_ITEMS[mode, len(items) == 1], count=f"{len(items):,}", place=place)
        )
        return f"{whole}; {links}" if links else whole
    parts = [
        *([say("{count} kept at the source", count=f"{kept:,}")] if kept else []),
        *([say("{count} failed", count=f"{failed:,}")] if failed else []),
        *([say("stopped")] if halted else []),
        *([say("{count} not attempted", count=f"{missing:,}")] if missing else []),
        *([links] if links else []),
    ]
    sentence = say(
        _SOME_FILES[mode, total == 1], done=f"{done:,}", count=f"{total:,}", place=place
    )
    if parts:
        sentence += f"; {', '.join(parts)}"
    return sentence if stopped is None else f"{sentence}. {stopped}"


class FileCopy(_Files):
    name: PasteKindName = "file_copy"
    title = N_("Copy files")
    needs = N_("Tick files or folders to copy")
    doing = N_("Copying")
    done = N_("copied")
    mode: ClipboardMode = "copy"
    can_replace = True
    source_requires: Access = "read"
    changes_source = False


class FileMove(_Files):
    """Replace is withheld: two connections may name the same backing file,
    and replacing it before removing the source would remove the copy (D163)."""

    name: PasteKindName = "file_move"
    title = N_("Move files")
    needs = N_("Tick files or folders to move")
    doing = N_("Moving")
    done = N_("moved")
    mode: ClipboardMode = "move"
    can_replace = False
    # Moving removes the source file, which is what writing there means.
    source_requires: Access = "write"
    changes_source = True
