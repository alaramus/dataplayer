"""Words a source or a job writes, in the language of whoever asked (D226).

A route's own refusal is a code the browser words (D225). What a source writes
— an action's title, a field of its form, a preview, a reason — belongs to the
source, which brings its translations with it, so the server words it here. The
key of a translation is the English itself: an adapter keeps writing English,
and a language lacking a sentence shows the English rather than nothing.
"""

from collections.abc import Callable, Mapping
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Literal, get_args
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Receive, Scope, Send

# The languages the interface speaks (D224). Here rather than with the
# account's preference because the server needs it on every request, and
# `users` may import `core` but not the other way round.
Language = Literal["en", "ru", "de"]
LANGUAGES: tuple[Language, ...] = get_args(Language)

current_language: ContextVar[Language] = ContextVar("current_language", default="en")

# Every language's translations, English text to translated text, merged from
# what each package registers. English has none: the key is the English.
_CATALOGS: dict[Language, dict[str, str]] = {language: {} for language in LANGUAGES}


def as_language(value: str | None) -> Language | None:
    for language in LANGUAGES:
        if language == value:
            return language
    return None


# English one package translates one way and another package another. The
# catalogs are merged, so the last to register would win where nobody chose.
_DISAGREEMENTS: list[tuple[Language, str, str, str]] = []


def register(language: Language, messages: Mapping[str, str]) -> None:
    """Add a package's translations. Called by the package as it is imported,
    the way an adapter registers itself."""
    known = _CATALOGS[language]
    for english, translated in messages.items():
        if english in known and known[english] != translated:
            _DISAGREEMENTS.append((language, english, known[english], translated))
    known.update(messages)


def disagreements() -> list[tuple[Language, str, str, str]]:
    """Each English two packages translate differently: the language, the
    English, and both translations."""
    return list(_DISAGREEMENTS)


def catalog(language: Language) -> Mapping[str, str]:
    return _CATALOGS[language]


def N_(text: str) -> str:  # noqa: N802 — the conventional name of gettext's marker
    """Mark English that is worded later, where it is shown — an action's title
    read when actions are listed — so the completeness test finds it."""
    return text


def say(text: str, /, **params: object) -> str:
    """English in the language of the request, its `{name}` parameters filled.

    Parameters are data and are not translated: a word passed as one reaches
    the sentence in English.
    """
    template = _CATALOGS[current_language.get()].get(text, text)
    return template.format(**params) if params else template


def say_if(text: str | None) -> str | None:
    return None if text is None else say(text)


# What a JSON schema says to a person: Pydantic's `title` and `description`,
# and the labels of `x-ui-choices`, how a form names what it offers.
_WORDED_KEYS = ("title", "description")


def say_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """A form's schema with the words a person reads translated.

    Only the keys that are words: a property's name, a default or an example
    is data, and an `enum` value is what is sent back.
    """
    copied = deepcopy(dict(schema))
    _translate(copied)
    return copied


def _translate(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _WORDED_KEYS and isinstance(value, str):
                node[key] = say(value)
            elif key == "x-ui-choices" and isinstance(value, list):
                for choice in value:
                    if isinstance(choice, dict) and isinstance(choice.get("label"), str):
                        choice["label"] = say(choice["label"])
            elif key != "properties":
                _translate(value)
            else:
                # Property names are identifiers; their schemas are words.
                for child in value.values():
                    _translate(child)
    elif isinstance(node, list):
        for item in node:
            _translate(item)


def requested_language(header: str | None, query: str | None) -> Language:
    """The language a request asks for: `?lang=` first, since a browser cannot
    set a socket's headers, then the first supported tag of Accept-Language."""
    named = as_language(query)
    if named is not None:
        return named
    for part in (header or "").split(","):
        tag = part.split(";")[0].strip().lower().split("-")[0]
        language = as_language(tag)
        if language is not None:
            return language
    return "en"


class RequestLanguage:
    """Sets `current_language` for everything a request or a socket does."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        header = headers.get(b"accept-language", b"").decode("latin-1")
        query = _query_value(scope.get("query_string", b""), "lang")
        token = current_language.set(requested_language(header, query))
        try:
            await self.app(scope, receive, send)
        finally:
            current_language.reset(token)


def _query_value(raw: bytes, name: str) -> str | None:
    values = parse_qs(raw.decode("latin-1")).get(name)
    return values[0] if values else None


def in_language[T](language: Language, work: Callable[[], T]) -> T:
    """Run `work` as if a request had asked for `language` — for a test, or for
    text written where no request is."""
    token = current_language.set(language)
    try:
        return work()
    finally:
        current_language.reset(token)
