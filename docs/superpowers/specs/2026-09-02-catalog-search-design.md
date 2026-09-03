# Searching the catalog by name

## Goal

Phase 3.5's search item, narrowed to the half that was asked for: find a node
by its name anywhere below the folder being looked at. Searching the *text
inside* files was dropped from this slice and asked for a day later; it is the
follow-up at the end, and it did not change anything decided here.

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

Codes are added when a screen has had to ask, not in advance. There were one;
the follow-up below made it two.

## Follow-up: the same search, held down, reads the files

Asked for the next day, so the thing that was "a different request" got its
answer: it is a different request and therefore a second capability
(`SearchesContents`), a second code (`content_search`) and a second route
(`catalog/search-contents`) — not a flag on the first. A source that lists
names without being able to read them answers 501 to it, and a client that
reads codes rather than prose never offers the gesture there.

What it is *not* is a second result shape. The answer stays `CatalogNode`s,
one per file, carrying the first line that matched in `NodeMatch.excerpt` — so
the whole argument above still holds: the list, the menu, the tick boxes and
Details needed nothing new, and a found row opens the way a listed one does.
"Every hit in a file, the way an editor lists them" would have been the other
result shape, and it is still a later slice.

The line replaces the caption a row would otherwise show. A file's size is
what the catalog says about it when nothing better is known; when the reason
the row is on screen is a line of text, that line is what is known.

Two gestures on one button rather than two buttons: the words are the same
words in the same field, so Shift-clicking the search (or Shift+Enter in the
field) is the same question asked of a second place. A separate button would
be a second control for a second answer to fill in nothing new.

**Its cost is stated before it is paid.** Minutes rather than milliseconds is
enough of a difference that a keypress should not spend it silently, so the
first one asks, says what it will skip, and offers to stop asking. The answer
lives in this browser's `localStorage`: it is a habit rather than a fact about
the data, nothing on the server needs it, and a browser that will not store it
simply asks again — the safe half of the choice. Ticking the box and then
cancelling remembers nothing; that is not an agreement to anything.

Reading has ceilings of its own on top of the walk's three:

| Bound | Value | Why |
| --- | --- | --- |
| per file | 8 MB | past that it is somebody's data set, not something being grepped |
| per search | 256 MB read | a folder of large files stops rather than running for minutes |
| excerpt | 200 characters | a log line or a minified document is one line and can be enormous |

A file that looks binary is skipped by the same test the content viewers use.
Skipped files are counted and the count is said, because "nothing matched" and
"a picture and a database dump were never opened" are different answers — the
same distinction `complete: false` draws for the walk.

## Deliberately not in this slice

- **Searching inside containers.** A workbook's sheets and an archive's entries
  are nodes, but finding them means opening files while walking.
- **Paging.** Past the ceiling the answer is the first N and a notice.
- **PostgreSQL.** Relation names across schemas are one `ILIKE` away; the
  capability is there, and 501 is the honest answer until it is written.
