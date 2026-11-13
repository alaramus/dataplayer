# The agent reads the user's guide

2026-11-13. D359.

## What was asked

A person asks the agent how DataPlayer works — where a button is, what a
source type can do, how a pipeline is scheduled — and the agent answers from
the application's own documentation rather than from what a model happens to
believe. The guide covered connections and source types only; the rest of the
application had no page.

## D359. A tool reads the guide a page or a section at a time

- **A tool, not the prompt.** `read_guide(key?, section?)` answers the outline
  without a key — every page's key, title and `## ` headings — the whole page
  with a key, and one section with both. The English pages alone are about
  140 KB and grow with every source; put in the system prompt they would be
  paid for on every turn of every chat, most of which never ask about the
  application. Section reads exist because a source page is 10–15 KB and a
  question is usually about one heading of it.
- **Search finds it too.** The guide is already a provider of the one search
  offered to the agent (D197, D199), so `search` with the words of a question
  returns the pages that hold them, and the agent reads the section it needs.
  No second index, and no model of meaning required: search by meaning runs
  only where its model is started (D220), and the guide must answer on every
  installation.
- **The person's language.** The page is read in the language the person
  speaks to the agent, the English where a page has no translation (D227), so
  the button names the agent repeats are the ones on their screen. An outside
  agent at `/mcp` reads English.
- **No transfer flag.** The guide is the application's own text and no
  connection's data, so D135 does not stand in front of it; it is offered at
  `/mcp` as a read like the others (D357).
- **The prompt sends questions there.** One line tells the agent to answer
  questions about DataPlayer from the guide and to name buttons as it does.
- **The guide covers the application.** Pages for the overview, the workspace,
  pipelines, dashboards, the agent, search, services and terminals, and
  preferences, written as the existing ones are: for the person using the
  screen, in the screen's words, from what the screens say and do rather than
  from the architecture files, which describe the code.

Rejected: the whole guide in the system prompt (above); a retrieval index of
embedded passages (it needs the optional model, and the guide is small enough
to navigate by headings); the architecture documents as the agent's source
(they are about the code, name internals a person never sees, and would
mislead an answer about a screen).

Known deviation: the new pages are English only at first. A person in another
language reads them in English in the guide's window; the agent answers in
theirs either way.

## Slices

One: the tool, its place at `/mcp`, the prompt's line, the eight pages, tests.
