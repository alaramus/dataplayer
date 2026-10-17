# Words a source writes

Date: 2026-10-17. Decisions: D226, D227.

After the screens moved to dictionaries (D224) and route refusals to codes
(D225), what remained English was written by the sources themselves: an
action's title and question, the labels of its form, previews, results,
reasons, job steps — some 1800 sentences across the adapters.

## Who words a source's sentence

Two ways were weighed.

- Codes, as for refusals: the adapter sends a key and parameters, the browser's
  dictionaries word it. Every adapter's vocabulary would then live in the
  frontend, so a new source type could no longer be a package of its own (D2),
  and the agent, which reads the same titles and results, would need English
  from somewhere else.
- The server words it in the language the request names, from translations the
  package keeps beside its code.

The second was chosen. The key is the English text, gettext-style, rather than
an identifier: an adapter goes on writing English, most class-level titles and
form labels need only a marker, and a missing translation degrades to the
English instead of to a key. Translating at the point of the response, not
over the whole body, keeps data — a table named `Name` — from being taken for a
word.

The language travels with each request: the interface's language as
`Accept-Language`, because the browser's own header says what the browser was
set to, and `?lang=` on sockets. What is stored — a job's step, a run's
message — would ideally be kept as English and worded when read; for now it is
worded when written, a recorded deviation.

A test reads the source of each moved package and fails on words nobody could
translate and on English without its translation, so a package once moved
cannot drift back.

## The rest

Dates and numbers follow the interface's language. The agent is told the
account's language. The guide keeps a page per language with the English
behind it, and is translated when it changes less often. A database's own
errors are passed on as written: the database's language is its own setting,
which DataPlayer does not control, and the English text is what is searched
for.
