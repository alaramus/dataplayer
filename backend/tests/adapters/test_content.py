from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.adapters.content import JsonContent, JsonLine, JsonScalar


@pytest.mark.parametrize(
    "content",
    [
        lambda: JsonContent(),
        lambda: JsonContent(
            value=JsonScalar(kind="null", value=None), source_text="null"
        ),
        lambda: JsonLine(line_number=1),
        lambda: JsonLine(
            line_number=1,
            value=JsonScalar(kind="null", value=None),
            source_text="null",
        ),
    ],
)
def test_json_results_carry_exactly_one_form(content: Callable[[], object]) -> None:
    with pytest.raises(ValidationError):
        content()
