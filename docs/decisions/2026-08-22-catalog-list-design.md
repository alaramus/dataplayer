# Catalog as a list, connections without a menu

Date: 2026-08-22
Status: agreed
Subproject: 7c (continuation of 7b)

## Goal

The layout from 7b is three columns that are always there. Their content is
still what was inherited from the earlier screens: the catalog tree from a
modal window, a row of action buttons above it, a three-dot menu in every
connection row. This worked while the catalog was a separate full-screen
window, and stopped working in a column a quarter of its width.

The task is to bring the content of the columns to the form in which they are
used every day: a list instead of a tree, a checkmark instead of a click at
random, one place for actions instead of a row of buttons, and a height bounded
by the screen.

## What changes in earlier decisions

No decision is revoked; three are refined.

**D2a stays and gets applied on screen.** "Sources differ in the node kind, not
in the source family" has so far affected only the backend. Now the screen
decides by node kind too: the schema multiselect appears not because this is
PostgreSQL, but because the children of the level are nodes of kind `schema`.
See S4.

**D9 is extended.** The question "what can be done with this node" becomes the
question "what can be done with all these nodes". The server still answers, and
the very same call still decides what is offered to the client and what is
allowed on the server. See S6, S7 and S8.

**D11 is not violated, but the kit loses a consumer.** The `AppTree` tree was in
the kit for the sake of the catalog; the catalog no longer uses it. The
component stays in the kit and in `/ui-kit` — the kit is built as an alphabet,
not by the number of current consumers — but this is recorded honestly under
"Known deviations".

## Decisions

### S1. A connection row is an icon, a name, a state, and nothing else

`ConnectorList` loses the three-dot menu. Three things remain in the row: the
source type icon, the name and the state dot. A click on the icon opens the
connection window, a click on the rest of the row opens the catalog.

The reason is not saving space, although the column is narrow. A menu in a list
row is a second place where the same actions live: check and delete are already
inside the connection window or should be there. While there are two of them,
they diverge — a check from the menu puts the result in a toast, a check from
the window puts it as a line next to the fields, and these are two different
stories about the same thing.

The state dot stays exactly as it is: grey until the user asks for a check. A
live status is work for the websocket of subproject 7+, and until it exists the
dot must not pretend to know more.

### S2. The source type icon is a file, not a font glyph

`adapterIcon()` returns `img:/icons/services/<file>.svg`. The files are taken
from the old application, which already has 103 of them, and put into
`frontend/public/icons/services/`. Only those needed today are carried over —
PostgreSQL and file storage; the rest arrive together with the adapters that
need them.

An unknown type still gets the `cable` glyph. The type registry lives on the
server and grows without rebuilding the frontend, so a missing file is a normal
state, not a build error.

The function stays pure and is tested without mounting, as it was.

### S3. There is one connection window, and deletion lives in it

`ConnectorDialog` is not split into "new" and "edit": it is one component, and
the difference between the two cases is only whether the fields are filled and
the title. That is how it already works; the decision records that it will stay
so, and moves inside what was left outside.

In the bottom row: `Delete` on the left, red, only when there is something to
delete; `Cancel`, `Check`, `Save` on the right. Deletion asks for confirmation,
forgets the check record and closes the window — what `ConnectorsPanel` does
today moves to where the connection itself is shown.

A new connection is opened by the "+" button in the column header. A button
with a label does not fit in a column a fifth of the screen wide.

### S4. The catalog is a list of one level, and the node kind decides what to do with a node

The tree is replaced by a list. The list shows the children of one node; the
header holds the path and an "up" button. What happens to a node is decided by
its kind — the table of kinds lives on the frontend next to the table of icons
in `treeNodes.ts`:

| Kind | What it is | What a click does |
| --- | --- | --- |
| `schema` | a grouping, not a place | not a list row at all: an item of the multiselect in the header |
| `directory` | a container | we go inside |
| `table`, `view`, `file` | something that is read | a tab in the right column |
| `column` | belongs to a table | not shown in the list |

The key point is that the table is indexed by node kind, not by adapter type.
The screen nowhere asks "is this PostgreSQL?". When ClickHouse with databases or
Kafka with namespaces appears, a row is added to the table, and the multiselect
comes out on its own.

A schema as a filter rather than a level is what the old application was used
for every day: the tables of two or three schemas are visible in one list, and
there is no need to go back up a level to move from `public` to `sales`.
Choosing several schemas means as many `list_children` requests as schemas
chosen; the list is their union, and the schema name stands as a caption on the
row, otherwise two tables with the same name are indistinguishable.

What is chosen on opening: the first schema not marked `is_system`, and if
there is none — the first in the list. An empty multiselect would mean an empty
list when the catalog opens, and all schemas chosen at once — a request for
each, `pg_catalog` included. System schemas are not removed from the
multiselect: they can be chosen, they are just not chosen by default.

The "up" button is disabled at the root level: there is nowhere to go above the
root.

Table columns disappear from the catalog. A click on a row keeps one meaning,
and the columns are visible where they are needed — in the header of the data
grid on the right. It was the same in the old application.

The name filter is an input field in the header, a substring, over the loaded
level only. No server-side search is introduced: it is not in the adapter
contract, and it would have to be added to everyone at once.

### S5. Marking and opening are different gestures

Every row has a checkbox, the list header has a "select all" checkbox. A single
click on a row (not on the checkbox) opens: a directory — going inside, a
readable node — a tab on the right.

The separation is needed for directories. While a click both selected and
opened, a folder could not be renamed without going into it — the action would
apply to the "current node", not to what the user is looking at. The checkbox
separates these, and also gives what did not exist at all: deleting ten files
in one action.

Moving to another level clears the marks. A mark is about what is visible now;
surviving the move, it would mean an action on something no longer on screen.

### S6. One menu in the header, and it has a target

The `ActionBar` row of buttons disappears. Actions are gathered into a
three-dot menu in the catalog header. The target of an action is read like this:

- nothing marked — **the current node**: these are `New folder` and `Upload`,
  which apply to the directory being looked at;
- one marked — that node;
- several marked — all the marked ones.

Buttons in a row were fitting while the catalog took the whole screen. In a
column they wrap onto a second line, and with five actions onto a third, and
the header eats the list.

An action over several nodes: the form is filled once, there are as many calls
as nodes, performed one after another. Refusals are collected and reported in
one line — "Deleted 4 of 5: summary.csv — folder is not empty". The branches
named in the responses' `reload_node_id` are reloaded once each at the end, not
after every call.

### S7. What can be done with a set of nodes is asked in one call

`GET /connectors/{id}/actions?node_id=…` is replaced by
`POST /connectors/{id}/actions` with the body `{"node_ids": [...] | null}`. The
response is the actions applicable **to each** of the listed nodes; `null`
means the root, as an omitted parameter meant before.

A read is expressed through POST for the same reason `fetch` is: the input is a
list of opaque identifiers whose length is unbounded. "Select all" in a
directory of five hundred files is five hundred identifiers, and there is no
room for them in the query string. Asking one node at a time is five hundred
requests instead of one; computing the intersection on the client means the
client decides applicability, which D9 does not allow.

The order of actions in the response is the order in which the driver returns
them, as it was.

### S8. Bulk use is declared by the action, and the client does not know about it

`Action` gets `bulk: ClassVar[bool] = False`. `Delete` declares `true`.
`Rename` does not: one name for five files is meaningless. `CreateFolder` and
`Upload` apply to a container, and the question does not arise for them in a
set of marked nodes.

The flag does not go out into the API. When a request has more than one node,
the server itself leaves out the actions that did not declare bulk use. The
client still knows exactly one thing: here is what can be done with what is
marked. This is the same rule by which the connector root does not return
`rename` — applicability is decided on the server, entirely.

### S9. The connector icon in the catalog header

On the left of the catalog header stand the source type icon and the
connection name. A click on the icon opens the same connection window as a
click on the icon in the first column.

The point is not convenience but that the connections column can be collapsed.
While editing a connection is reachable only from it, a collapsed column cuts
off access to the settings of what is being worked with now.

### S10. A section gives a panel a box, the panel decides what moves in it

`workspace-leaf__body` stops scrolling itself (`overflow: hidden`) and becomes
a box of fixed height. What stays in place inside and what scrolls is decided
by the panel.

Today the whole panel scrolls, header included: the path, the multiselect and
the grid paginator all move away. The panel knows it has a header, while the
engine does not know and must not — it has no notion of "panel header", and
introducing one for this would give the engine knowledge of what panels show.

All three panels are built the same way: the header stays, the body moves. In
the data grid the table header is sticky, the paginator is pinned to the bottom
outside the scroll. The page as a whole never scrolls.

### S11. A collapsed section shows a chevron and nothing more

The reason the "expand" button disappeared: the tab strip has
`overflow: hidden`, the tabs come before the spacer and the chevron, and in the
twenty-eight pixels of a collapsed column the chevron is pushed past the edge.
The connections column has a wide tab — there it never appeared; for the others
it depended on the length of the title, hence "sometimes".

A collapsed section does not render tabs at all: only the chevron at the full
height of the strip, with a name tooltip. The tab strip gets `min-width: 0`, the
button `flex: none`, so that it is not pushed out in a narrow expanded column
either.

## What is not done

- **Live connection status.** The dot knows only about a manual check. Polling
  over the websocket is subproject 7+.
- **Server-side search and sorting of the catalog.** The name filter works over
  the loaded level. The adapter contract knows neither.
- **Paging of catalog children.** The file source still refuses to list a
  directory of more than 2000 entries. A cursor changes the contract for all
  adapters at once.
- **Moving and copying.** An action works inside one node of one connection —
  as it did.
- **Remembering the place in the catalog.** The layout survives a reload, but
  the path inside the catalog does not: after a reload the root is open.

## How it is checked

| What | By what |
| --- | --- |
| `adapterIcon` returns a file path, an unknown type gets a glyph | `bun run test:unit` |
| the table of node kinds: `schema` is a filter, `column` is not shown, what is read | `bun run test:unit`, a pure function |
| intersection of actions over a set of nodes, `bulk` filters out `Rename` | `uv run pytest tests/` |
| `POST /actions` with one node answers as the old `GET` did | `uv run pytest tests/` |
| an action not in the set does not resolve | the existing test, 404 |
| a connection row has no menu; a click on the icon opens the window | Playwright |
| deleting a connection is done from the window | Playwright |
| select all, delete several, see the report | Playwright |
| each of the three columns collapses and expands | Playwright |
| the page does not scroll, the column body scrolls | Playwright, the document's `scrollHeight` |
