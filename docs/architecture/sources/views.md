# A view of a document

For a source that describes a node in a JSON document of its own — Docker's
inspect, a topic's configuration, an object's metadata — and wants to say what
that document means. How a node opens at all is [content.md](content.md)
(D47); the JSON tree beside a view is D295 there. Docker's views are D422 in
[docker.md](docker.md).

Decisions here: D419, D420, D421.

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
  for `tree`. `TreePanel` has the button back. The two replace each other in
  the same tab: one binding draws both and picks the component as it draws
  (`panels.ts`), and `switchRepresentation` rewrites the panel in place. A
  content panel carries the node's `representations` only where one is a
  view, so a stored panel of any other kind is unchanged. A representation
  drawn by another kind of tab (a table) opens that tab. The choice is not
  remembered: the node opens on its first representation again.
- **A link opens what the catalog would.** A `link` value carries a node id
  of the same connection, never taken apart (D21); the client reads the
  source's path to it, shows a level in the catalog and opens a node that
  opens by its first representation.
- **Read only.** A view shows; a node's actions stay in the catalog's menu
  (D9).
- **Bounded.** At most 200 blocks, counting a section's children; a table of
  at most 500 rows; pairs and a list at most 500; a text value at most 16 KB,
  cut with `truncated` rather than refused. Past a ceiling the block carries
  `omitted`, and the client says that many are in the JSON.

Known deviations:

- **Only Docker's container has a view.** Image, volume and network are the
  next slice (D422).
- **Opening the inspect node is not opening the container.** A container is
  walked into (D408), so a click on it shows Inspect, Logs and Processes, and
  Inspect opens on the view. The spec asked whether a book (D51) could open
  its first page's representation; it can — `openRepresentation` takes the
  first of the node's own list — but a container opened as a book would lose
  its Logs, which is why D408 walks in. The container node itself declares
  `[view, tree]` too, so opened from a search or a link it opens on the view.

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
