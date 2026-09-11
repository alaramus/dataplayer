# The freshness window a connection chooses

## Problem

D31 gave the source the freshness rules, because the source is the only party
that knows them. In practice the source knows one thing — whether its answers
may be reused at all — and guesses the other. PostgreSQL keeps a catalog level
for thirty seconds and a page of rows for ten. Those numbers were chosen for a
database somebody is browsing. They are wrong in both directions for the
databases people actually connect: a reporting replica that changes nightly is
read again every ten seconds for nothing, and a queue table somebody is
watching is ten seconds stale when they wanted none.

Nobody could change them without editing the driver, which means one number for
every connection of that type, held by every user of the deployment.

There is a second, separate complaint behind the first. A screen that shows a
cached answer looks exactly like a screen that shows a fresh one. Somebody
watching a grid cannot tell whether the rows in front of them were read now or
kept, so they reload out of doubt — which is the cost the cache was supposed to
save.

## What the connection decides, and what it does not

`Connector.cache_ttl_seconds` is nullable. Null is the source's own window,
which is what every connection made before the column existed still means, and
zero is no caching at all.

Two parties, and only one of them may say yes. The source still decides whether
its answers may be cached — a driver that does not implement `SupportsReadCache`
is read directly however long its owner would like to keep an answer, because
nobody has written down what its answers mean over time. Where the source did
opt in, its owner decides for how long. A number in a form cannot make an
uncacheable source cacheable; it can only shorten or lengthen a window the
source already offered.

The window covers what somebody is looking at: catalog levels and pages of
rows. It deliberately stops short of `metadata`, which is what an editor
completes against. That area is a description of a whole database, re-read as
one unit and thrown away by any change to the connection. Tying it to the ten
seconds somebody chose for their rows would spend a full description of the
database on every suggestion list, and the person who set that number was
thinking about their rows.

Which areas the window covers is decided in one function, `connector_may_choose`,
matched over the closed set of areas. A fourth cache area fails to type-check
until somebody says which side of the line it is on. Every caller passes the
window, including the metadata route that will not get to use it, so no route
is a second place where the rule is written.

The ceiling is one day. Any staleness beyond that is not a cache but a copy,
and a ceiling means a typo of one extra zero cannot pin a page there for a
week.

## Changing it takes effect at once

Nothing new was needed for that. Editing a connector already invalidates its
entries and its loads in flight (D31), and the window is part of the connector.
A person who shortens the window and reloads is not looking at an answer stored
under the old one.

## Saying how old the answer is

`X-Data-Cache` already said where an answer came from and nothing read it.
It now travels with `X-Data-Cache-Age`, the seconds since the source was
actually read: zero whenever the reply is the read, and the entry's age on a
hit.

Age is reported rather than worked out by the reader, because neither end knows
it alone. The screen knows when the answer reached it; only the cache knows how
long the answer had been sitting there first. Adding the two is what makes a
grid able to say the rows in front of you were read four minutes ago — through
a browser cache in front of a server cache, neither of which the other can see.

The memory backend stores the moment it wrote the entry. The shared backend
reads the remaining life of the key in the same round trip as the value, and
subtracts: what is left of the life it was stored for is what it has already
spent. Redis owns that clock, so no worker's own time of day takes part in the
answer, and no cache value had to change shape — D101's wire format is
untouched.

## What the screen does with it

The badge says `Live` while the answer is a read of the source and nothing has
aged since, and how long ago otherwise — a page read four minutes ago is not
live any more, whatever the reply said when it arrived. Its tooltip says both
the age and what the connection's window is. It sits beside the reload it
explains, in the grid header and above a catalog level, and pressing it
reloads: the answer to "is this stale?" and the way to do something about it
are the same control.

It is drawn only where there is something for it to report. A file source
never opted into caching, so every page of it is a read of the source and a
badge over it would say "Live" for ever — which is not information but a
promise about a cache that does not exist. The same holds for a connection
whose owner chose to keep nothing. So the screen asks two questions before
drawing anything: does this kind of source cache at all, and did this
connection refuse. An unanswered question counts as no, because the lists
arrive a moment after the panel and a badge that appears late is easier to
read than one that appears and then goes away.

The freshness travels inside the cached value rather than beside it. A map of
statuses kept next to vue-query would be a second cache with its own eviction,
and the desynchronisation that follows is what D7 exists to avoid. So a row
page in the client cache is `{ page, freshness }` and a catalog level is
`{ nodes, freshness }`.

One clock ticks for the whole application, shared by every badge, because a
timer per badge in a workspace of twenty tabs is twenty timers saying the same
second.

The window itself is set on a page of the connection window called Options,
added for it. It is not a connection parameter and not a permission, and a
form asks how to reach a source before it asks how the source behaves — so
the field belongs behind a tab rather than beside the name.

The default option says durations, not a policy. "As the source decides" is a
sentence about an inside the person filling in the form has never seen: it
tells them nothing about whether their rows will be a second or ten minutes
old. So each source type publishes what it keeps its own answers for —
`cache_windows`, derived from the driver exactly as its capabilities are, and
absent for a source that never opted in — and the option reads "As this source
decides (rows 10s, lists 30s)". For a source that keeps nothing the field says
the source is always read live and is switched off, because no window typed
there would change anything, and a control that accepts a choice it will not
honour is worse than one that is not there.

That the published windows are the ones the field can replace is not left to
care: the model's fields and the areas `connector_may_choose` admits are
compared in a test, so a fourth overridable area is offered and described
together or not at all.

## What this is not

It is not polling. A window decides whether a stored answer may be reused when
somebody asks again; it does not make an open panel ask. A grid that re-reads
itself on a timer is the auto-refresh button, which already exists, is per
grid, and holds its tick while a cell is being edited or rows are ticked. The
two were deliberately left separate: one is about how old an answer may be, the
other about how often to ask, and a screen that started polling because its
owner lengthened a cache window would be doing something nobody asked for.

## Evidence

Backend unit tests: a source that never opted in is not cached by a window; the
window replaces the source's for catalog and fetch and not for metadata; zero
turns the connection off; a hit reports the age the entry actually has, in both
backends. Route tests: a connection told to keep nothing bypasses on every
read, a reply says the age it carries, an explicit null hands the window back
to the source and caching resumes, and a window past the ceiling is refused.
The frontend tests the label and the tooltip as pure functions, and the badge
is asserted in the browser, because a caption that is computed and never
rendered is the mistake this project has already made once.
