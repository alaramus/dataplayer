"""An S3 store as a source: the file explorer over its objects (D150, D379).

Everything the file source does is the explorer's and comes with it; what is
here is the store: how it is reached and which actions it offers.
"""

from typing import ClassVar

from app.adapters.explorer.actions import (
    EXPLORER_ACTION_TYPES,
    ConnectFolder,
    ExplorerActionType,
)
from app.adapters.explorer.explorer import Explorer
from app.adapters.registry import AdapterContext, register
from app.adapters.s3.options import S3Options
from app.adapters.s3.storage import S3Storage
from app.core.translation import N_


class S3Adapter(Explorer):
    """The explorer over one bucket, or over every bucket a key may list."""

    # A folder never becomes a connection of its own: the draft would carry
    # the key to the browser, as an SSH folder's would carry its password.
    explorer_action_types: ClassVar[tuple[ExplorerActionType, ...]] = tuple(
        action_type
        for action_type in EXPLORER_ACTION_TYPES
        if action_type is not ConnectFolder
    )

    def __init__(self, options: S3Options, context: AdapterContext) -> None:
        self._options = options
        super().__init__(S3Storage(options))


@register(
    name="s3",
    title=N_("S3"),
    category="files",
    description=N_(
        "Amazon S3 or a store that speaks its API. Browse buckets and folders "
        "and work with objects as with your own files: tables, SQL over files, "
        "the editor, archives, search and copying between connections. Buckets "
        "are made and deleted here too. Signs in with an access key."
    ),
    options_schema=S3Options,
    adapter_class=S3Adapter,
)
def _build(options: S3Options, context: AdapterContext) -> S3Adapter:
    return S3Adapter(options, context)
