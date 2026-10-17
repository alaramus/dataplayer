# Localization

Date: 2026-10-11. Decisions: D224, D225.

The whole application was written in English: templates, toasts, constants in
TypeScript modules and the sentences the server refuses with. The goal is a
language chosen in Preferences, Russian first, then German, French and
Chinese.

## Where the words live in the browser

vue-i18n, the standard for Vue, with dictionaries as TypeScript modules rather
than JSON. A module typed `Messages` — the shape of the English — makes a
missing or extra key a type error, which JSON cannot do without a second tool.
vue-i18n's typed-schema augmentation was tried first: it types the
dictionaries but its `t` still accepts any string, and a mistyped key compiled
and showed itself on screen. A wrapper `t` taking only the English keys closes
that, and `useI18n` is forbidden so nobody goes around it.

English is bundled; other languages are lazy chunks, because five languages of
a few thousand strings each would otherwise all be downloaded by everybody.

Quasar ships its own strings (a table's "Rows per page", a date picker's
months) and its own language packs; the pack is switched with the
dictionaries.

## Where the choice lives

On the account, beside the other preferences. The theme was kept in the
browser (D6) because it suits a screen; a language suits a person, who should
not choose it again on every machine. Not choosing is a state of its own —
follow the browser — rather than a default of English, so a person who never
opens Preferences still gets their language when the interface speaks it.

The sign-in page knows nothing of the account. The browser remembers the last
language applied and opens sign-in in it, and the application mounts only once
that chunk is loaded: mounting first would draw English and then turn it over.

## The server's sentences

Two ways were weighed.

- The server translates: it reads `Accept-Language` or the account's choice
  and answers in it, with gettext catalogues in the backend. Fewer changes, but
  translations then live in two places, and the server has to know the
  person's language on every request, sockets included.
- The server names the refusal and the browser words it. One place for
  translations, the same one the screens use.

The second was chosen. A refusal is a code from one closed set, parameters, and
the English. The English stays because the API has readers that are not the
browser: logs, the agent's tools, scripts. The browser uses it as it is for
English, so English is written once, on the server; the other languages are
dictionaries keyed by the code. The code set is published through OpenAPI as
the `4XX` answer of every route, which makes the dictionaries' completeness a
type check on the frontend. Declaring the schema once for the whole router
costs a line per operation in the generated client and is true: any route can
refuse.

Parameters are names and numbers only. A kind of failure passed as an English
word would arrive untranslated inside a Russian sentence; such a thing is a
code of its own.

## Moving over

The change is large — some four thousand strings in two hundred and fifty
screens, and nearly four hundred refusals on the server — so it is done in
portions, a feature at a time. Until a screen moves it stays English in every
language. ESLint's `no-raw-text` is switched on per directory as each moves,
so a moved screen cannot regain English text; the list ends as `src/**`.

The first portion is the frame — dictionaries, the choice, plural rules, the
coded refusal and its checks — with sign-in, Preferences and the account
routes moved over as the pattern.
