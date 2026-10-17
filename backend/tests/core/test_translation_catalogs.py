"""Every word a moved package writes has its translations (D226).

The packages already moved are listed, the way ESLint's list of screens grew;
it ends as every package that writes for a person.
"""

import ast
import string
from collections.abc import Iterator
from pathlib import Path

import pytest

import app.main  # noqa: F401 — imports every package, so every catalog registers
from app.core.translation import LANGUAGES, Language, catalog

APP = Path(__file__).resolve().parents[2] / "app"

MOVED: list[str] = [
    # "adapters/postgres" — moving now
]

# Class attributes and Field arguments that are words a person reads. Each is
# read where it is shown, so it is written `N_("…")` to be found here.
WORDED_ATTRIBUTES = {"title", "question", "description", "category_title"}
WORDED_FIELD_ARGUMENTS = {"title", "description"}
# Arguments that carry a sentence to a person wherever they are passed: the
# result of an action, why it is unavailable, what a preview says. A literal or
# an f-string there was written in English and never worded.
WORDED_ARGUMENTS = {
    "message",
    "reason",
    "unavailable_reason",
    "summary",
    "notice",
    "question",
    "caption",
    "label",
    "title",
    "description",
    "doing",
    "done",
    "step",
}


def _files() -> Iterator[Path]:
    for package in MOVED:
        yield from sorted((APP / package).rglob("*.py"))


def _is_call(node: ast.AST, *names: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
    return name in names


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _is_english(node: ast.AST) -> bool:
    """A sentence written in place: a literal, or the fixed part of an
    f-string, with a letter in it. `f"{schema}.{name}"` is data; a name, an
    attribute or a call is data or already worded."""
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(part, ast.Constant) and any(c.isalpha() for c in str(part.value))
            for part in node.values
        )
    text = _literal(node)
    return text is not None and any(character.isalpha() for character in text)


def _findings() -> tuple[set[str], list[str]]:
    """The English each moved file marks, and every place it writes words
    that nobody could translate."""
    marked: set[str] = set()
    problems: list[str] = []
    for path in _files():
        if "locales" in path.parts:
            continue
        where = path.relative_to(APP)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if _is_call(node, "N_", "say") and isinstance(node, ast.Call) and node.args:
                text = _literal(node.args[0])
                if text is None:
                    problems.append(f"{where}:{node.lineno} the first argument of N_/say must be a literal")
                else:
                    marked.add(text)
            if (
                isinstance(node, ast.Call)
                and not _is_call(node, "Field", "N_", "say")
            ):
                for keyword in node.keywords:
                    if keyword.arg in WORDED_ARGUMENTS and _is_english(keyword.value):
                        problems.append(f"{where}:{node.lineno} {keyword.arg}=… is English nobody words")
            if _is_call(node, "Field") and isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg in WORDED_FIELD_ARGUMENTS and _literal(keyword.value) is not None:
                        problems.append(f"{where}:{node.lineno} Field({keyword.arg}=…) is not marked N_")
            if isinstance(node, ast.ClassDef):
                for statement in node.body:
                    target, value = None, None
                    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                        target, value = statement.targets[0], statement.value
                    elif isinstance(statement, ast.AnnAssign):
                        target, value = statement.target, statement.value
                    if (
                        isinstance(target, ast.Name)
                        and target.id in WORDED_ATTRIBUTES
                        and value is not None
                        and _literal(value) is not None
                    ):
                        problems.append(f"{where}:{statement.lineno} {node.name}.{target.id} is not marked N_")
    return marked, problems


def test_every_word_a_moved_package_writes_is_marked() -> None:
    _, problems = _findings()
    assert problems == []


TRANSLATED: list[Language] = [language for language in LANGUAGES if language != "en"]


@pytest.mark.parametrize("language", TRANSLATED)
def test_every_marked_word_has_its_translation(language: Language) -> None:
    marked, _ = _findings()
    translations = catalog(language)

    missing = sorted(text for text in marked if text not in translations)

    assert missing == []


@pytest.mark.parametrize("language", TRANSLATED)
def test_a_translation_keeps_the_parameters_of_its_english(language: Language) -> None:
    """A `{name}` lost or renamed in translation raises when the sentence is
    filled, in front of the person reading it."""
    def names(text: str) -> set[str]:
        return {field for _, field, _, _ in string.Formatter().parse(text) if field}

    wrong = [
        english
        for english, translated in catalog(language).items()
        if names(english) != names(translated)
    ]

    assert wrong == []
