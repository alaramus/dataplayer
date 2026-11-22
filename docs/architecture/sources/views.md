# A view of a document

For a source that describes a node in a JSON document of its own — Docker's
inspect, a topic's configuration, an object's metadata — and wants to say what
that document means. How a node opens at all is [content.md](content.md)
(D47); the JSON tree beside a view is D295 there. Docker's views and pages
are D422–D423 in [docker.md](docker.md).

Decisions here: D419, D420, D421, D424.

## D419. A node may open as a view of its document

**`view` is a representation kind** beside `tree`, declared in a node's ordered
`representations` (D47) like any other. A node that offers one declares it
first and its document second: `[view, tree]`. A node without a view opens as
before.

- **The source builds it.** `read_content` with `representation="view"`
  answers a `DocumentView`, a member of the content union, from the same
  document it answers as `tree`. No second request to the server it reads.
- **The client draws it knowing no source.** `ViewPanel`
  (`features/content/view/`) renders any `DocumentView` by its blocks, with no
  code per source type, node kind or field. A new source's view is a function
  in its adapter and no client change.
- **The document is one click away.** The view's head has a button for each
  other representation the node declared, in the source's words: **As JSON**
  for `tree`. It opens a tab of its own named `<node> — <title>` (D424); the
  view's tab stays. A content panel carries the node's `representations` only
  where one is a view, so a stored panel of any other kind is unchanged.
- **Other pages open separately.** A `DocumentView` may carry source-owned
  `pages`, each with a node id, title and ordered representations. `ViewPanel`
  draws one button per page and opens its preferred representation in a new
  tab named for the node and page. Because pages arrive with the view, a node opened from search or a link gets
  the same buttons without a client rule for its source.
- **A link opens what the catalog would.** A `link` value carries a node id
  of the same connection, never taken apart (D21); the client reads the
  source's path to it. A node without readable content shows its level in the
  catalog; an openable node opens by its first representation.
- **Read only.** A view shows; a node's actions are run as anywhere else,
  through the action's own window (D9). The ones the source puts over the
  view are D424.
- **Bounded.** At most 200 blocks, counting a section's children; a table of
  at most 500 rows; pairs and a list at most 500; a text value at most 16 KB,
  cut with `truncated` rather than refused. Past a ceiling the block carries
  `omitted`, and the client says that many are in the JSON.

Known deviations:

- **Only Docker has views** (D422): its container, image, volume and network.
- **Docker pages are no longer catalog levels** (D423). Its nodes open
  directly on their view; the view advertises the separate table pages. A
  linked or searched Docker node resolves to the same view and buttons.

Spec: [A view of a document](../../decisions/2026-11-21-document-views-design.md)

## D420. The blocks of a view

`DocumentView` (`app/adapters/views.py`) is Pydantic with `extra="forbid"`
throughout, its blocks and its values discriminated unions, so a block the
client cannot draw fails on the server. Every word in it is the source's,
through `say()`; every value is already what is shown.

- **Header** — once: a title, a subtitle that is any value (Docker's image is
  a link) and an optional **state**: a word and a **tone** from `good`,
  `busy`, `warning`, `bad`, `neutral`. The kit turns a tone into the theme's
  colour (`stateTone` in `tokens.ts`, `AppStateTag`); neutral is muted text,
  not a fifth message colour.
- **Section** — a title and blocks under it, possibly `collapsed` when it
  opens. Sections do not nest: the type of a section's children leaves the
  section out.
- **Fields** — labels and values. A value is one of `text`, `code`
  (monospaced, with a copy button), `number` with an optional unit, `bytes`
  (the reader's units), `moment` (date and how long ago), `duration`,
  `boolean`, `state`, `list` (chips), `link` and `empty` (a dash, so "not set"
  is told from "not shown").
- **Pairs** — names and values, filterable past twenty; a pair may be
  sensitive (D421).
- **Table** — named columns and rows of values, one per column, checked. An
  empty table keeps its columns and says it has none.
- **Notice** — a sentence with a tone.

A block is never a layout instruction: no widths, no columns of the page. A
number that is an identifier — a port — is sent as text, since a number is
drawn with the reader's grouping.

Where it lives: the blocks read the client's types, so they sit in
`features/content/view/` beside the panel; what any screen could use — the
state with its tone — is in the kit as `AppStateTag`. The `/ui-kit` showcase
draws every block and value kind from `sample.ts`, which the unit tests mount
too.

Spec: [A view of a document](../../decisions/2026-11-21-document-views-design.md)

## D421. A sensitive value is hidden until asked for

The source marks a pair sensitive; the view draws it as dots with an eye that
shows it, and its copy button works only once it is shown. A filter over the
pairs never matches a hidden value, which would say what it is.

This hides from a glance, not from a reader: the value arrives with the view,
and the JSON beside it shows it plainly. That is no new exposure — whoever
opens the view can open the JSON — and the guide keeps saying that anybody
the connection is shared with sees a container's environment. Withholding the
value from a grantee would be a decision about the document itself, not about
views.

Spec: [A view of a document](../../decisions/2026-11-21-document-views-design.md)

## D424. A view's head: icons, the node's actions, separate tabs

Every command in a view's head is an icon whose title is its tooltip and its
accessible name, as the workspace's toolbars are. In order: the node's
actions, the other representations, the pages, then the panel's own reload,
reveal and window.

- **The source names the pictures.** `ViewPage.icon` is a Material Symbols
  name; a page without one is drawn by its first representation's icon. A
  representation's icon is the client's (`REPRESENTATION_ICONS`), as in the
  catalog. Docker's Logs is `receipt_long` and Processes `dns`, the pictures
  of the workspace's own logs and services.
- **Actions over the view.** An action declaring `in_view` (and an `icon`) is
  also drawn over the view of a node it is applicable to, asked by
  `readActions` for that one node. It opens the same window the catalog opens
  (`ActionDialog`), or the connection form for one that prepares a
  connection. The catalog keeps it: a ticked set is still acted on there.
  After it is done the catalog hears of the change and the view reads the
  node again; a node now answering 404 closes the tab rather than leaving one
  that cannot be read.
- **Every other representation opens a tab of its own,** named
  `<node> — <title>`, as a page does: the view and its JSON are no longer
  switched in one tab, and `switchRepresentation` is gone. One binding still
  draws both kinds, so a tab stored before this opens as it was saved.

Docker puts each container's lifecycle verbs, Remove, Commit to an image,
Terminal and Open as connection over its view. The lifecycle verbs also act on
a Compose project, which has no view.

Spec: [A view's head](../../decisions/2026-11-22-view-head-design.md)
