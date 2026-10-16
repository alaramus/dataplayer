# Localization

The language the interface speaks, and how what the server refuses with reaches
the reader in it. Read this before writing any text a person sees, adding a
language, or adding a refusal to a route.

Decisions here: D224, D225.

```
frontend/src/shared/i18n/
├── index.ts          the languages, `t`, loading one, which one opens first
├── problems.ts       a coded refusal told apart and worded
└── locales/
    ├── en/           the source, a module per area; every other language is typed against it
    └── ru/           the same areas in Russian, the server's refusals, and glossary.md

frontend/src/features/preferences/
├── GeneralSection.vue   the Language choice
└── AccountLanguage.vue  puts the account's choice on the interface

backend/app/core/problems.py   every refusal code and its English
backend/app/users/preferences.py   `language` on the account
```

English and Russian today; German, French and Chinese are planned.

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
first frame is not English. The theme stays in the browser (D6): it depends on
the screen, and the language on the person.

A string taken from `t` while a module loads is fixed in the language current
then. Constants a screen reads — section lists, theme names — hold their words
in getters, and a function returning words calls `t` when it is called.

Each language keeps a glossary beside its dictionaries — one word for one
thing, and its typographic conventions — so screens moved at different times
agree.

A message's syntax is vue-i18n's: `{name}` takes a parameter, `|` separates
plural forms, `@` and `$` must not appear bare. The order of plural forms in a
language other than English is in `PLURAL_FORMS`, judged by the browser's
`Intl.PluralRules`: Russian lists `one | few | many | other`. A unit test runs
every message of every language through vue-i18n's compiler.

ESLint's `no-raw-text` fails on text written into a template, or into an
attribute a person reads, in the directories already moved to dictionaries;
the list in `eslint.config.js` grows until it is `src/**`. Words in `.ts`
modules are not seen by it and rest on review.

### Known deviations

- Most screens are still English: sign-in, Preferences, the workspace, the
  panel engine, the catalog and the component kit are moved. A language shows
  English wherever a screen has not moved.
- Text a source declares — action titles and their questions, parameter
  labels, menu groups, previews, report captions — is English in every
  language: it comes from the adapters, which have no dictionaries.
- Dates and numbers are formatted by the browser's locale, not by the chosen
  language.
- The user's guide (D183) is English only.
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
