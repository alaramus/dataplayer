"""The table engines a designed ClickHouse table may be kept by (D274).

The MergeTree family and the small engines that keep rows as they arrive. The
replicated and distributed ones are left out: each needs a cluster or a
ZooKeeper path, which is configuration of the server rather than of a table.
"""

from dataclasses import dataclass

from app.adapters.table_design import EngineOption, EngineParameter
from app.core.translation import N_, say

_UNSIGNED = ["uint8", "uint32", "uint64"]
_NUMBERS = ["int8", "int16", "int32", "int64", *_UNSIGNED, "decimal", "float32", "float64"]


def _version(required: bool, type_codes: list[str]) -> EngineParameter:
    return EngineParameter(
        code="version", title=N_("Version column"), required=required, type_codes=type_codes
    )


_SIGN = EngineParameter(code="sign", title=N_("Sign column"), required=True, type_codes=["int8"])


@dataclass(frozen=True)
class Engine:
    option: EngineOption
    # Parameter codes in the order the engine takes its arguments.
    order: tuple[str, ...] = ()

    def worded(self) -> EngineOption:
        option = self.option
        return option.model_copy(
            update={
                "description": say(option.description) if option.description else None,
                "parameters": [
                    parameter.model_copy(update={"title": say(parameter.title)})
                    for parameter in option.parameters
                ],
            }
        )


def _engine(
    code: str,
    description: str,
    *,
    sorted_rows: bool = True,
    merges: bool = False,
    parameters: tuple[EngineParameter, ...] = (),
) -> Engine:
    return Engine(
        EngineOption(
            code=code,
            # The engine's own name: it is what the documentation and every
            # statement call it.
            title=code,
            description=description,
            sorted=sorted_rows,
            merges_by_key=merges,
            parameters=list(parameters),
        ),
        tuple(parameter.code for parameter in parameters),
    )


ENGINES: dict[str, Engine] = {
    engine.option.code: engine
    for engine in (
        _engine("MergeTree", N_("Rows kept in the order of the primary key; the usual choice")),
        _engine(
            "ReplacingMergeTree",
            N_("Rows sharing the primary key are merged into the latest, or the one of the highest version"),
            merges=True,
            parameters=(_version(False, [*_UNSIGNED, "date", "datetime", "datetime64"]),),
        ),
        _engine(
            "SummingMergeTree",
            N_("Rows sharing the primary key are merged into one, their numbers added up"),
            merges=True,
            parameters=(
                EngineParameter(
                    code="columns", title=N_("Columns to add up"), many=True, type_codes=_NUMBERS
                ),
            ),
        ),
        _engine(
            "CollapsingMergeTree",
            N_("A row written with sign -1 cancels the earlier one with the same key"),
            merges=True,
            parameters=(_SIGN,),
        ),
        _engine(
            "VersionedCollapsingMergeTree",
            N_("Rows cancel each other by sign, matched by key and version"),
            merges=True,
            parameters=(_SIGN, _version(True, _UNSIGNED)),
        ),
        _engine("Log", N_("Small tables written at once and read whole"), sorted_rows=False),
        _engine("StripeLog", N_("Small tables of many columns written at once"), sorted_rows=False),
        _engine("TinyLog", N_("The smallest tables, written once"), sorted_rows=False),
        _engine("Memory", N_("Kept in memory only; gone when the server restarts"), sorted_rows=False),
    )
}

DEFAULT_ENGINE = "MergeTree"
