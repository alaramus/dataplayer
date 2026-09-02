# Searching the catalog by name

## Goal

Phase 3.5's search item, narrowed to the half that was asked for: find a node
by its name anywhere below the folder being looked at. Searching the *text
inside* files is dropped from the roadmap rather than deferred — see the end.

## Where it goes on the screen

The catalog already has a text field, and it already means "narrow this". The
shape decided here keeps that and adds one thing to it:

> The words are typed as they are now and filter the level as they do now. Once
> there are words, a search button appears beside them; pressing it asks the
> source to look everywhere below.

One input, two questions. The alternative — a search field of its own — makes
somebody type the same word twice and then decide which box they meant.

While results are shown, the list is not a level any more, so it says what it
is showing and offers the way back. The words stay in the field: closing the
search returns to the folder with the same text filtering it, which is exactly
the state the search was launched from.

## Decision

**D76. A search is a read of the catalog, and the words are the filter's.** The
statement, its consequences and the known deviations are in
[the source contract](../../architecture/sources/contract.md).

The result is `CatalogNode`s — the same ones the listing gives, from the same
builder, which was extracted from the file catalog for exactly this. So a found
row has its icon, its caption, its viewers, its actions and its Details, and
the list, the menu and the tick boxes needed no notion of a search at all. The
only thing a match adds is where it was found.

## Why nodes and not "hits"

A search that answered its own shape — a path, a score, a snippet — would need
a row that draws it, a click that opens it, a menu that acts on it and a
Details that describes it. Four screens' worth of second implementation, all
for rows the catalog can already draw. The one thing that is genuinely new is
the location, and that is one field.

## What bounds it

A walk of a tree is unbounded by nature, so three ceilings hold it, and the
answer says which one stopped it:

| Bound | Value | Why |
| --- | --- | --- |
| matches | 100 by default, 500 at most | what a person reads |
| entries looked at | 100,000 | a personal directory is not a filesystem |
| depth | 24 | a tree deeper than that is a mistake or a loop |

Breadth first, so what is near is found first: a ceiling then cuts the far end
of the search rather than a random branch of it, and the first hundred matches
are the hundred closest to where the question was asked.

`complete: false` with a notice is the whole difference between "nothing else
matched" and "I stopped looking", and only the second is a reason to type more
words. A count with no such flag would say the first and mean the second.

## Safety

- **The query is matched, never compiled.** A case-insensitive substring of a
  name — D2c's rule about client strings, stated for the one input this takes.
  There is no pattern language to escape, so a `*` is a character in a name.
- **A symbolic link is listed and never walked into**, whatever it points at.
  An alias can duplicate a tree into the results or point at its own parent,
  and a search is exactly where a loop shows up. The recursive archive walk
  already refuses links for that reason; this is the same refusal.
- **Containment is judged before a single entry is listed**, by the one rule
  (D8), and every node that comes back goes through the builder that answers
  None for anything resolving outside the root.

## How the client knows whether a source can search

`Capability` gained a `code` from a closed set beside the title it already had.
A title is written to be read and may be reworded tomorrow; a screen that
switched on one would be branching on prose, which is the pattern the migration
notes list under "must not be ported". The code is still derived by `issubclass`
in `capabilities_of`, so nothing is listed by hand and a driver that stops
implementing the protocol stops claiming the capability in the same commit.

Codes are added when a screen has had to ask, not in advance. There is one.

## Deliberately not in this slice

- **Text inside a file.** Removed from the roadmap at the user's decision. It
  is a different request with a different answer — lines, not nodes — needing
  its own result shape, its own ceilings and a way to stand at a line rather
  than at a node.
- **Searching inside containers.** A workbook's sheets and an archive's entries
  are nodes, but finding them means opening files while walking.
- **Paging.** Past the ceiling the answer is the first N and a notice.
- **PostgreSQL.** Relation names across schemas are one `ILIKE` away; the
  capability is there, and 501 is the honest answer until it is written.
