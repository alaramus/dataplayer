"""D66's closed families, recognised by a statement's leading words (D383).

Used only where the dialect's parser gave a statement no class. The words
only take away: a match refuses, and a statement they do not match still meets
the strictest gate an unclassified statement has. That is why this is not the
first-word classification D62 rejects, which is about admitting.
"""

from collections.abc import Mapping, Sequence

# How many leading words a family is named by, at most.
LEADING = 3


def refusal_by_words(
    words: Sequence[str], families: Mapping[tuple[str, ...], str]
) -> str | None:
    """The sentence of the longest family these leading words open, if any.

    A tokenizer may keep a phrase as one token — sqlglot's MySQL reads
    `LOCK TABLES` so — which is why every token is split again here.
    """
    upper = tuple(
        part.upper() for word in words[:LEADING] for part in word.split()
    )[:LEADING]
    for length in range(len(upper), 0, -1):
        found = families.get(upper[:length])
        if found is not None:
            return found
    return None
