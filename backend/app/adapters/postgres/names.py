"""What a name typed into a form must be before it can become an identifier.

One rule, because it is one rule: PostgreSQL allows 63 bytes for a name of any
kind, and a name that is empty or padded with spaces is a mistake whatever it
names. The three things a form here asks the name of — a relation, a schema, a
role — differ only in the word for what is being named, so that word is the
parameter and the rule is written once rather than copied a third time.

Refusing is not quoting. What a person did mean to type is made safe by
`psycopg.sql.Identifier`, which every caller still composes with; this only
turns away what nobody means.
"""

from collections.abc import Callable

# PostgreSQL truncates rather than refuses beyond this, which is worse than a
# refusal: a name silently becomes another name.
NAME_LIMIT_BYTES = 63


def name_check(subject: str) -> Callable[[str], str]:
    """A field validator for the name of one kind of thing.

    A factory rather than a function taking two arguments, because Pydantic
    calls a field validator with the value alone.
    """

    def check(value: str) -> str:
        if value == "" or value != value.strip():
            raise ValueError(
                f"A {subject} name cannot be empty or start or end with spaces"
            )
        if len(value.encode("utf-8")) > NAME_LIMIT_BYTES:
            raise ValueError(
                f"A PostgreSQL {subject} name cannot exceed "
                f"{NAME_LIMIT_BYTES} bytes"
            )
        return value

    return check
