"""How a sample-data script shipped with a source is cut into statements.

The scripts are this project's own (D245, D280), written so that a semicolon
at the end of a line ends a statement and nothing else does: no body in them
holds a semicolon of its own. So a script is split on that rule alone, rather
than by a parser that would have to know every dialect's quoting.
"""

import re

_END = re.compile(r";[ \t]*\r?\n")


def statements_of(script: str) -> list[str]:
    """The script's statements, its comment lines left out."""
    text = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("--"))
    return [statement.strip() for statement in _END.split(text + "\n") if statement.strip()]
