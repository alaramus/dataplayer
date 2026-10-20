# Localization

The language the interface speaks, and how what the server refuses with reaches
the reader in it. Read this before writing any text a person sees, adding a
language, or adding a refusal to a route.

Decisions here: D224, D225, D226, D227.

```
frontend/src/shared/i18n/
├── index.ts          the languages, `t`, loading one, which one opens first
├── format.ts         dates and numbers in the interface's language
├── problems.ts       a coded refusal told apart and worded
└── locales/
    ├── en/           the source, a module per area; every other language is typed against it
    ├── ru/           the same areas in Russian, the server's refusals, and glossary.md
    ├── de/           the same areas in German, the server's refusals, and glossary.md
    └── fr/           the same areas in French, the server's refusals, and glossary.md

frontend/src/features/preferences/
├── GeneralSection.vue   the Language choice
└── AccountPreferences.vue  puts the account's language and theme on the interface

backend/app/core/problems.py   every refusal code and its English
backend/app/core/translation.py   the request's language; say, N_, say_schema
backend/app/<package>/locales/ru.py   a package's own words in Russian (de.py in German, fr.py in French)
backend/app/users/preferences.py   `language` on the account
```

English, Russian, German and French today; Chinese is planned.

## D224. The interface speaks the account's language, from typed dictionaries

Every word a person reads comes from a dictionary through `t` in
`@/shared/i18n`. English is the source and is built in; every other language
is a chunk loaded when somebody chooses it, with Quasar's own pack beside it.
Each language is typed as `Messages`, the shape of the English, so a key one
language lacks or has extra fails `bun run type-check`. `t` takes only keys
English has; vue-i18n's own `t` takes any string and shows a mistyped key as
the key, so `useI18n` is forbidden by ESLint.

The language is the account's (`language` in `/users/me/preferences`), so it
follows the person to any browser. None is a choice of its own: the browser's
language, or English when the browser asks for nothing the interface speaks.
Before sign-in nothing is known about the account, so the browser remembers
the last language applied (`dataplayer-language`) and the sign-in page opens in
it; the application is mounted only once that language has loaded, so the
first frame is not English. The theme is kept the same way, on the account
with the browser holding the last one: `AccountPreferences` applies both once
the account is read and saves a theme chosen anywhere — Preferences, the
welcome, the toggle — so two people sharing a browser each get their own.

A string taken from `t` while a module loads is fixed in the language current
then. Constants a screen reads — section lists, theme names — hold their words
in getters, and a function returning words calls `t` when it is called.

Each language keeps a glossary beside its dictionaries — one word for one
thing, and its typographic conventions — so screens moved at different times
agree.

A message's syntax is vue-i18n's: `{name}` takes a parameter, `|` separates
plural forms, `@` and `$` must not appear bare. The order of plural forms in a
language other than English is in `PLURAL_FORMS`, judged by the browser's
`Intl.PluralRules`: Russian lists `one | few | many | other`, French
`one | other`. A unit test runs
every message of every language through vue-i18n's compiler.

ESLint's `no-raw-text` fails on text written into a template, or into an
attribute a person reads, in every `.vue` under `src` but the developer pages
in `features/dev`, which no build ships. Words in `.ts` modules are not seen
by it and rest on review.

### Known deviations

- Text saved with a thing is in the language it was made in: a new
  dashboard's name, a widget's title made from what was ticked, a new
  project's name.
- Text a source declares — action titles and their questions, parameter
  labels, menu groups, previews, report captions — is English in every
  language: it comes from the adapters, which have no dictionaries.
- Dates and numbers are formatted by the browser's locale, not by the chosen
  language.
- The user's guide (D183) has Russian, German and French pages; a page a
  language lacks is shown in English (D227).
- The agent answers in whatever language it is written to; it is not told the
  account's.

Spec: [Localization](../decisions/2026-10-11-localization-design.md)

## D225. A server refusal is a code with parameters; the browser words it

A route refuses with `Problem(status, code, **params)` from
`app.core.problems`. The body is
`{"detail": {"code": ..., "params": {...}, "message": "English"}}`. The codes
are one closed `Literal`, published through OpenAPI on every route's `4XX`
answer, so the generated client has `ProblemDetail["code"]` and each language's
`problems` dictionary is a `Record` over it: a code added on the server and not
translated fails the frontend's type check.

The English is sent too and lives only on the server: logs, the agent's tools
and anyone calling the API read it, and the browser shows it as it is when the
interface is English, or when a newer server sends a code this build lacks.
Parameters are data — a name, a number — and never a word, because a word in a
parameter would arrive in English inside a translated sentence.

`messageOf` words a coded refusal before any other shape of `detail`.

A refusal about a source carries `error_kind` beside its code — `config` for a
capability the source lacks, a result that could not be stored — and
`errorKindOf` reads it there as from an adapter failure, so `retry.ts` does
not ask again. A capability is its own code (`connectors.no_search`), not a
word passed to one.

### Known deviations

- Coded so far: the account, sign-in, connector, access, action, declared
  reference, SSH key, paste, query, agent, metrics, service, backup, pipeline,
  share, search, search index, transfer, job, source operation and guide
  routes. Every other route still refuses with an English sentence, shown as
  English in every language until it is coded.
- A refusal that passes on another module's sentence stays English: a write
  the connection's policy refuses (D66), a statement refused by its source, the
  dashboards' setup, an agent's refusal to run, the text of a `ValueError`
  or `NodeNotFound` an adapter raised, the container runtime's reason it cannot
  run (a service, a backup's program, its storage volume), a service engine's
  refusal, a backup source's reason it cannot be copied, and a pipeline run
  that names the links lacking something (`Nothing ran: …`, with `link_ids`).
- An action's title is passed as `{action}` in several codes, so it reaches a
  translated sentence in English until actions are translated.
- A validation failure (422) is FastAPI's list with Pydantic's English `msg`;
  its `type` is a code the browser could word, and does not yet.
- Adapter failures reduced by `classify` carry an English message and a kind,
  not a code.

Spec: [Localization](../decisions/2026-10-11-localization-design.md)

## D226. What a source writes is worded on the server, in the language asked for

An action's title and question, the fields of its form, a preview, a result,
why something is unavailable, a job's step: an adapter writes these, and a new
source type is a new package (D2), so its words come with it rather than into
the browser's dictionaries. Each package keeps `locales/ru.py`, English to
Russian (and `de.py`/`fr.py` beside it), and registers it as it is imported. The key is the English itself:
the adapter keeps writing English, the agent's tools still read English, and a
language that lacks a sentence shows the English.

The browser names the interface's language on every request —
`Accept-Language` on HTTP, `?lang=` on a socket, which cannot carry headers —
and `RequestLanguage` sets `current_language` for everything the request
does. `say(text, **params)` words a sentence; `N_(text)` marks English read
later where it is shown, as a class's `title` is read when actions are
listed. Routes word what they pass on: `say(action.title)`, and
`say_schema(...)` over a form, which translates `title`, `description` and the
labels of `x-ui-choices` and leaves names, defaults and enum values as data.
When the interface changes language, cached server answers are read again.

`tests/core/test_translation_catalogs.py` fails, in every package of `app` but
the few it names with their reason, on a
worded class attribute or `Field` argument not marked `N_`, on a literal or an
f-string with words passed as `message=`, `reason=`, `summary=` and their
like, on marked English without a translation, and on a translation whose
`{name}` parameters differ from the English, and on English two packages
translate differently — the catalogs are merged, so the last to register
would otherwise choose. A sentence returned or raised any other way rests on
review.

### Known deviations

- Text a job or a pipeline run stores — its steps and messages — is worded
  when it is written, in the language of whoever started it, rather than kept
  as English and worded when read. Work no request started — a scheduled
  pipeline run, recovery at start, the search keeper — writes English.
- Two transfer steps, "waiting for a free transfer slot" and "removing the
  sources", stay English: the browser recognises them by their text and words
  them itself.
- Pydantic's own validation messages, and a parser's or a database's text
  passed on inside a sentence, are English.
- Names the server makes up for a new thing — "Metrics store", "SSH server 1",
  "New chat" — are stored in English; "New chat" is worded where it is shown.
- The agent's prompts, tool descriptions and tool results stay English: the
  model reads them. What its tools show the person is worded.
- A socket's language is the one it connected in; what it carries after a
  switch is in the old language until it reconnects.

Spec: [Words a source writes](../decisions/2026-10-17-source-words-design.md)

## D227. Dates, numbers, the agent, the guide and a database's own errors

Dates and numbers are formatted in the interface's language, not the
browser's. The agent is told the account's language and answers in it unless
it is written to in another. The user's guide (D183) keeps a page per language
and shows the English where a page has no translation. A database's own error
text — PostgreSQL's `relation "x" does not exist` — is passed on as the
database wrote it: its language is the server's setting, and the English is
what a person searches for.

- A date or a number a person reads goes through `@/shared/i18n/format`:
  `formatDateTime`, `formatDate`, `formatTime`, `formatNumber`, and
  `formatFixed` in place of `toFixed`. A fixed locale is kept only where the
  output must not change with the language, and says why.
- The runner takes `current_language` when a run starts or resumes and passes
  it to `system_prompt(language)`; quick chat words its prompt the same way.
  English adds no line.
- A translated guide page is `pages/<language>/<key>.md` (D183); a key English
  lacks is refused when the pages are read.

An email is written in its recipient's language: the one their account chose,
or the language of the request that sends it — a new account's is its
maker's. Each template is one file whose sentences are `{{ say("…") }}`,
worded from `core/locales/ru.py` with the subject; the catalog test reads the
templates and fails on a sentence typed into the markup.

### Known deviations

- A chart takes ECharts' locale when it is drawn (`shared/i18n/echarts.ts`);
  one already on screen keeps its axis words until it is drawn again.
- A grid cell is data and is shown as the source sent it, not reformatted.
- Chinese pages do not exist yet; a language without a page shows
  the English. Russian, German and French pages exist (D227).

Spec: [Words a source writes](../decisions/2026-10-17-source-words-design.md)

