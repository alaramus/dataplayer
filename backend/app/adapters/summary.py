"""What a source says about one node, apart from its rows and its content.

Three questions already have answers. A viewer says what is inside a document
(D47); a relation model says what shape a table has; an action says what may be
done to a node. None of them answers the plainest question of all — how big is
it, since when, what may it be opened as, and what does its format state about
itself — and a node with no viewer and no columns has no answer at all without
this one (D75).

The facts a format states are a discriminated union rather than labelled
strings, for the reason `DatasetInfo` is one: a screen rendering "name: value"
pairs written by the source would show text nobody could check. Two of its
members are `DatasetInfo`'s own, because a Parquet file states the same things
here as it states there, and one computation belongs in one place.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.catalog import NodeKind, ReportNode
from app.adapters.content import (
    AudioMediaType,
    ImageMediaType,
    NodeRepresentation,
    VideoMediaType,
)
from app.adapters.dataset import ParquetDataset, WorksheetDataset
from app.adapters.delimited import DelimiterName
from app.adapters.fetch import Filter
from app.adapters.relation import Persistence, RelationKind
from app.adapters.specializations import RelationSpecialization
from app.adapters.timescale_metadata import TimescaleFacts

# What the bytes turned out to be, rather than what the name promised. A file
# that is not UTF-8 says so instead of being decoded with replacements and
# called text.
TextEncoding = Literal["utf-8", "utf-8-bom", "not-utf-8"]

# Said by counting, not by the platform: a file written on one system is read
# on another, and "mixed" is a fact worth seeing rather than an average.
LineEndings = Literal["lf", "crlf", "cr", "mixed", "none"]


class TextContents(BaseModel):
    """A file read as lines, whatever its name promises it holds."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    encoding: TextEncoding
    lines: int | None = Field(default=None, ge=0)
    longest_line_bytes: int | None = Field(default=None, ge=0)
    line_endings: LineEndings | None = None
    # Why the counts above are absent. A stated ceiling beats a guessed count,
    # and every counting member here carries the same field for the same
    # reason.
    not_counted: str | None = None


class DelimitedContents(BaseModel):
    """A delimited file, counted with the parser that reads it as rows.

    Its rows are counted by `csv` rather than by newlines: a value in quotes
    may hold a line ending, and a count that ignored that would disagree with
    the grid beside it.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["delimited"] = "delimited"
    # Absent rather than a character a reader has to recognise. The set is
    # closed by the sniffing rule in `delimited.py`.
    delimiter: DelimiterName | None = None
    # Both absent together with the reason: a file that was not read through
    # has a header and a width, and stating zero would be a count rather than
    # the silence it is.
    columns: int | None = Field(default=None, ge=0)
    # Data rows: the header is not one of them.
    rows: int | None = Field(default=None, ge=0)
    encoding: TextEncoding
    not_counted: str | None = None


class WorkbookContents(BaseModel):
    """A workbook, which holds sheets rather than one table (D51)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["workbook"] = "workbook"
    sheets: int = Field(ge=0)
    hidden_sheets: int = Field(ge=0)


class ArchiveContents(BaseModel):
    """An archive as its central directory declares it, inflating nothing."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["archive"] = "archive"
    entries: int = Field(ge=0)
    files: int = Field(ge=0)
    directories: int = Field(ge=0)
    # What the entries say they expand to, and what they take as they are.
    size_bytes: int = Field(ge=0)
    compressed_bytes: int = Field(ge=0)
    # Listed and never read, so worth counting where somebody is asking what is
    # in the file (D53).
    encrypted: int = Field(ge=0)
    links: int = Field(ge=0)


class EntryContents(BaseModel):
    """One member of an archive, which has no bytes of its own on disk."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["entry"] = "entry"
    compressed_bytes: int | None = Field(default=None, ge=0)
    encrypted: bool = False
    link: bool = False


class ImageContents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["image"] = "image"
    media_type: ImageMediaType
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class AudioContents(BaseModel):
    """What a sound file's header states, and nothing a decoder would know."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["audio"] = "audio"
    media_type: AudioMediaType
    duration_seconds: float | None = Field(default=None, ge=0)
    channels: int | None = Field(default=None, ge=1)
    sample_rate: int | None = Field(default=None, ge=1)


class VideoContents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["video"] = "video"
    media_type: VideoMediaType
    duration_seconds: float | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)


class PdfContents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["pdf"] = "pdf"
    version: str


class DirectoryContents(BaseModel):
    """What one level of a folder holds, at the cost of one listing."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["directory"] = "directory"
    entries: int | None = Field(default=None, ge=0)
    files: int | None = Field(default=None, ge=0)
    directories: int | None = Field(default=None, ge=0)
    not_counted: str | None = None


class RelationContents(BaseModel):
    """What a relation states about itself, apart from the shape of its rows.

    Deliberately not the relation model: that is a table column by column,
    constraint by constraint, and it has a screen of its own. This answers the
    plainest question instead — what is this thing, who owns it, how it is
    stored, how much of it there is, and when the server last looked at it.

    The counts are of the model that was read to build this, so a reader is
    told there are nine columns by the same query that would list them.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["relation"] = "relation"
    # Narrower than the node's kind, which calls a materialized view a view:
    # how a relation is stored is exactly what somebody opening this is asking.
    relation_kind: RelationKind
    specialization: RelationSpecialization | None = None
    timescale: TimescaleFacts | None = None
    schema_name: str
    owner: str | None = None
    persistence: Persistence | None = None
    comment: str | None = None
    columns: int = Field(ge=0)
    indexes: int = Field(ge=0)
    constraints: int = Field(ge=0)
    # Estimated on purpose, as everywhere else this number is given: an exact
    # count costs a full scan, and the name says so rather than pairing a
    # number with a flag about how true it is.
    row_estimate: int | None = Field(default=None, ge=0)
    # The only "since when" a relation has. PostgreSQL records neither when a
    # table was created nor when it was last written to, so the summary's own
    # question is answered with what the server does record: when its planner
    # statistics were last brought up to date, and when its dead rows were
    # last cleared. A view has neither.
    analyzed_at: datetime | None = None
    vacuumed_at: datetime | None = None
    # How a partitioned table is cut up, and what a partition is part of. Both
    # absent for a relation that is neither.
    partitioned_by: str | None = None
    partition_of: str | None = None


# Adding a format means adding a member here and a branch to the one place that
# renders them, which is a type error until it is written.
NodeContents = Annotated[
    TextContents
    | DelimitedContents
    | ParquetDataset
    | WorksheetDataset
    | WorkbookContents
    | ArchiveContents
    | EntryContents
    | ImageContents
    | AudioContents
    | VideoContents
    | PdfContents
    | DirectoryContents
    | RelationContents,
    Field(discriminator="kind"),
]


class RelatedView(BaseModel):
    """A source-issued report with editable initial filters (D121)."""

    model_config = ConfigDict(extra="forbid")

    node: ReportNode
    filters: list[Filter] = Field(default_factory=list, max_length=16)


class NodeSummary(BaseModel):
    """One node described by the source that holds it.

    The relational vocabulary a file has no notion of is absent rather than
    filled in, exactly as it is in `RelationModel`; so is a time the platform
    does not state. `contents` is empty for a node whose format says nothing,
    and `notice` says why when the format was expected to say something and
    could not — a `.zip` whose bytes are not one, which is the catalog's known
    deviation about a misleading suffix (D47) reaching the reader.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str
    kind: NodeKind
    # The same ordered answer the catalog gives, so "what can this be opened
    # as" is one list computed once (D47).
    representations: list[NodeRepresentation] = Field(default_factory=list)
    size_bytes: int | None = Field(default=None, ge=0)
    modified_at: datetime | None = None
    accessed_at: datetime | None = None
    # Only where the platform states a creation time. Where it does not, the
    # inode change time is a different fact wearing this one's name.
    created_at: datetime | None = None
    # The POSIX spelling, as `ls` writes it.
    permissions: str | None = None
    contents: NodeContents | None = None
    notice: str | None = None
    related_views: list[RelatedView] = Field(default_factory=list, max_length=16)
