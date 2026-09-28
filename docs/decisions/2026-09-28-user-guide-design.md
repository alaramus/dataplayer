# A user's guide, and the catalog's short lists

Date: 2026-09-28. Decision: D183. Changes what D13's capabilities are shown for.

## The problem

The **New connection** window showed, for the selected type, "What you can see"
and "What you can change" as chips built from `capabilities_of`: one chip per
capability protocol and per action class. PostgreSQL had thirty-two, eleven of
them TimescaleDB policies. Many named the driver's functions rather than what a
person does: "Locate a node", "Describe a relation", "Find what points here".
Others split one thing a person means into several: "Add columns", "Drop
columns", "Edit rows", "Insert rows", "Delete rows" are all "editing a table".

There was also no documentation for the person using the application at all:
how a screen works, where a command is, what a limit is. The agent will need the
same text later, to tell somebody where to press or to do it for them.

## D183. A source type has a page in the user's guide, and the catalog reads its short lists from it

**The guide is Markdown on the server.** `backend/app/guide/pages/` holds one
page per source type, `source-<type>.md`, and pages about the application,
`connections.md` first. The server owns them because the agent, which runs on
the server, is meant to read them; the browser reads them through
`GET /guide/` and `GET /guide/{key}`. They are written for the person using the
application — which window, which button, what happens, what the limits are —
and never about the code.

**The short lists are the page's own.** A source page opens with
`## What you can see` and `## What you can change`, each a list of one-line
items. The server reads those items and sends them on `GET /adapter-types` as
`can_see` and `can_change`. The panel and the guide therefore say the same
thing, and it is written in one place.

**Capabilities stay what screens switch on.** `capabilities_of` is unchanged
and keeps its codes. What changed is that a person no longer reads its titles:
the panel shows the short lists, and the catalog's search matches them instead
of the titles, since a match on a word nobody is shown cannot be explained.

**One guide window.** **Guide** in the panel opens a floating window on the
type's page. It is not modal, so it stays open while the connection form is
filled in. Links between pages are written `other-page.md`; the sanitiser keeps
them as relative links and the window turns to the page. A second **Guide**, or
a link, turns the same window, and Back returns to the page before.

**Held up by tests.** Every registered type has a page with at least one thing
to see; a short item is at most 80 characters, one line of the panel; every
link between pages names a page; a key that is not a page is 404, and a key is
never joined onto a path.

## Rejected

- **Grouping the derived capabilities into plain areas.** A table from protocol
  to area, and a field on every action class, would keep the list derived. But
  the words would be the same for every source, and "Table data and columns"
  means something else for Redis than for PostgreSQL; a person reads the
  source, not the protocol.
- **A short list written into `register()`.** A second copy of what the guide
  page says, in a different file, drifting from it.
- **The guide in the browser bundle.** The agent could not read it without
  shipping it twice.
- **A Markdown parser on the server.** The two lists are the top-level bullets
  under two headings; a line reader is enough, and a test pins the shape.

## Known deviations

- The guide is written by hand, so it can fall behind the driver. The
  capability list cannot; that is the trade.
- Only connections and the four source types have pages. The rest of the
  application is a later slice, and so is handing the guide to the agent.
- Links within a page (`#section`) are not followed by the window.
