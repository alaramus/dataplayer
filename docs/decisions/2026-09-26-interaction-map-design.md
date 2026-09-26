# A map of what the connections can do to each other

Date: 2026-09-26. Decision: D174. Builds on D97 (the graph document), D164
(one paste answer for a pair of connections) and D167 (a pair of catalogs).
Comes from the "graph of possibilities" deferred by the interactions design of
2026-09-25.

## The problem

What one connection can give another is answered today one pair at a time:
Paste in a catalog, or the bar of a pair window. Somebody with a dozen
connections cannot see at once that the SSH server takes files from personal
storage, that both databases save as CSV into either, that rows from all of
them can become a table in PostgreSQL — nor that a connection shared with them
read-only takes nothing. The answer exists on the server, per pair; nothing
draws it for all of them.

## D174. A map of the connections, and what each can give each other

### What it shows

- **A node for every switched-on connection the person sees**, named by it,
  captioned by its type and grouped by the type's category — databases,
  key-value stores, files — so the graph's own group filter narrows it.
- **One arrow per direction** between two connections that some kind of paste
  (D164) serves: source to destination, labelled with what it can do —
  "Copy files · Move files", "Save as CSV", "Create a table · Add rows to a
  table". Selected, the arrow lists each operation and whether it is open to
  this person.
- **What an arrow claims** is what the two connections can do, by what they
  are and the person's standing on each — never that a given file or table
  will go. Whether a selection goes is the pair window's answer, as now.
- **An arrow this person cannot use** — the destination is theirs to read
  only, say — is drawn dashed, and each operation says what it needs: "Needs
  write access to Reports". Hidden, it would leave nobody knowing what is
  missing.
- **Declared references are not drawn.** A line between data is not a
  possibility of transfer, and the interactions design keeps the two apart.

### Where it is, and what it does

- **A space of its own, "Connections map"**, beside Data, Dashboards and AI
  in the rail's switch (D125, D141): chosen, it fills the screen as they do.
  It is D97's viewer, 2D and 3D, with its search, selection and layout kept
  per person. A space rather than a tab of the data workspace, because it is
  about all the connections at once rather than about one of them; and it has
  no first panel, so the header's button for hiding one is not drawn there.
- **An arrow selected offers "Open as pair"**: the data space comes back and
  the pair window (D167) opens with the source on the left and the
  destination on the right, where ticking and the bar do the rest. **A node
  selected offers "Open catalog"**, and activating one opens it too.
- **Its reload button** asks again; a connection added, switched off or shared
  since is on it then.

### How it is answered

- **One request, `GET /interactions/map`**, answered from the paste registry:
  for every ordered pair of the person's connections, each kind whose
  `serves` holds, with the access it needs checked against the person's
  standing on each end. The same kinds, the same rule and the same reasons as
  Paste; nothing on the client knows a kind.
- **No connection is opened.** The adapters are built — which reads no source
  — and asked by capability. A connection whose options no longer read is a
  node with no arrows.
- **At most 300 connections**, the graph's own ceiling; beyond it the map is
  refused with the reason rather than drawn in part.

## Out of scope

- Arrows for a particular selection, for moves within one connection (D74),
  or for anything but paste kinds.
- Remembering or suggesting routes through several connections; pipelines.

## Known deviations, accepted with it

- **An arrow can promise what a node refuses.** "Save as CSV" from a database
  into a folder holds for its tables, not for a schema ticked by mistake; the
  pair window says so when it is asked.

## Acceptance

- With a PostgreSQL connection, personal storage and an SSH server, the map
  shows files copied and moved both ways between storage and the server, CSV
  saved from the database into each, and rows from each into the database.
- A connection shared read-only is an arrow's destination only dashed, with
  "Needs write access to …"; a switched-off one is not on the map.
- The map is a space of the rail's switch; "Open as pair" on an arrow returns
  to Data with the two catalogs as a pair, the source on the left.

Tests cover the answer for such a set of connections and for a read-only
grant, the ceiling, the graph built from an answer as a plain function, and
in the browser the map opened from the rail with a pair opened from an
arrow.

## Later

The map stopped being a screen when pipelines took its place on the rail
(D175, [Pipelines](2026-09-26-pipelines-design.md)); its answer stays, as the
first filter of the hint of possible links (D176).
