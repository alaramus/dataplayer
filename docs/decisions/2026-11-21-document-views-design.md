# A view of a document

Decisions D419–D422. A source that describes a node in a JSON document of its
own — Docker's inspect, a topic's configuration, an object's metadata — can
also say what that document means: a page drawn from a closed set of blocks,
with the document itself one click away. The contract is general (D419–D421);
Docker's container, image, volume and network are the first to use it (D422).

Facts marked *to check* were not tried when this was written and are probed
before the slice that depends on them.

## Why

Docker's Inspect is a tree of two to three hundred fields. What a person opens
it for — is it healthy, which ports, which image, what is mounted, which
variables — is a dozen of them, scattered three levels deep. Other sources
hold the same kind of document: a Kafka topic's configuration, a RabbitMQ
queue's arguments, an S3 object's metadata, a ZooKeeper node's stat and ACL,
a letter's headers, a server's version and settings. Each would otherwise grow
a screen of its own.

## Rejected: presets on the client

A list on the client of JSON paths per source type ("for `docker`, show
`State.Health.Status` as the state") is quicker for the first source and wrong
for every later one. The client would learn what each source's documents mean
and grow into a second adapter; the same value would be computed on both sides
(ENGINEERING.md: "the same computation in the backend and the frontend is a
defect"); its words would not go through `say()`; and a node id, which the
client treats as opaque (D21), would be read apart for the paths. The source already reads the document and knows what
`Config.Env` is, so it says it.

## A node may open as a view of its document (D419)

**A new representation kind, `view`**, beside `tree` (D295), declared in a
node's ordered `representations` (D47) like any other. A node that offers a
view declares it first and its document second: `[view, tree]`. Nothing else
in D47 changes — a node without a view opens as before.

- **The source builds it.** `read_content(ContentRequest(representation="view"))`
  answers a `DocumentView` (D420), a new member of the content union. The
  source reads the same document it would answer as `tree`; no second request
  to the server it reads is made for the view.
- **The client draws it knowing no source.** One panel, `ViewPanel`, renders
  any `DocumentView` from its blocks. It has no code per source type, per node
  kind or per field; a new source's view is a new adapter function and no
  client change.
- **The document stays one click away.** The view panel shows a button for
  each other representation the node declared — **Show as JSON** for `tree` —
  and reopens the tab with that one first, as the tree and source panels
  already do between text and table (*checked*: `TreePanel` gains the button
  back; the two replace each other in the same tab rather than opening a
  second one, through one binding that picks its component as it draws). The choice is not remembered per node:
  opening the node again opens its first representation.
- **Read only.** A view shows; it changes nothing. A node's actions stay in
  the catalog's menu (D9), and a view does not offer them again. Revisit when
  a source needs a button inside a view; the block would be an action by name,
  checked by the same route as the menu.
- **Bounded like any content.** A view is built from a document the source
  already bounds (Docker's inspect, D408); a view of at most 200 blocks, a
  table of at most 500 rows, a text value of at most 16 KB. Past a ceiling the
  block says how many were left out, and the JSON has them all.

## The blocks of a view (D420)

`DocumentView` is a Pydantic model with `extra="forbid"` throughout, its
blocks a discriminated union, so a block the client cannot draw fails
validation on the server rather than vanishing on screen (ENGINEERING.md,
Types). Every word in it is the source's, through `say()`; every value is
already what is shown — a size in bytes is a number and its kind, never a
string the client parses.

- **Header** — once, at the top: the title, a subtitle, and optionally a
  **state**: one word and a **tone** from a closed set (`good`, `busy`,
  `warning`, `bad`, `neutral`). The tone is a meaning; the client turns it
  into the theme's colour (design system: a screen asks for meaning).
- **Section** — a title and the blocks under it. Sections do not nest; a
  section may be **collapsed** when it opens, for a long one such as labels.
- **Fields** — label and value lines. A **value** is one of a closed set of
  kinds, the same everywhere a value appears:
  - `text`, and `code` — monospaced, with a copy button;
  - `number`, with an optional unit;
  - `bytes` — drawn in the reader's units;
  - `moment` — an instant, drawn as the date and how long ago;
  - `duration` — in seconds;
  - `boolean`;
  - `state` — a word and a tone, as in the header;
  - `list` — of short texts, drawn as chips;
  - `link` — text that opens another node of the same connection by its id
    (an image from a container, a volume from a mount); the client opens it
    as the catalog would open that node;
  - `empty` — the value is not there, drawn as a dash, rather than a field
    left out, so "not set" and "not shown" are told apart.
- **Pairs** — names and values, such as environment variables or labels,
  filterable when there are more than twenty. A pair may be **sensitive**
  (D421).
- **Table** — named columns and rows of the same values, for ports, mounts,
  networks, health checks.
- **Notice** — a sentence the source wants read, with a tone: "This container
  restarted 14 times".

A block is never a layout instruction (no widths, no columns of the page);
the client lays a view out, the source says what is in it.

## A sensitive value is hidden until asked for (D421)

The source marks a value sensitive; the view draws it as dots with a button
that shows it, and copying it needs the button first. Docker marks an
environment variable whose name holds `PASSWORD`, `PASSWD`, `SECRET`, `TOKEN`,
`KEY`, `CREDENTIAL` or `PRIVATE`, case-folded — a name, because the value
cannot be judged.

This hides from a glance, not from a reader: the value arrives with the view,
and the JSON beside it shows it plainly, as Inspect does today. That is no new
exposure — whoever opens the view can open Inspect — and the guide keeps
saying that anybody the connection is shared with sees a container's
environment. Withholding the value from a grantee would be a different
decision about Inspect itself, not about views.

## Docker's views (D422)

The container's **Inspect** view (D408) and the container node itself declare
`[view "Overview", tree "As JSON"]` (*checked*: a book, D51, opens by the
first of its own representations; a container is not a book but walked into,
D408, so a click on it shows Inspect, Logs and Processes, and Inspect opens
on the view — opened from a search or a link, the container itself does). The view is built from the inspect the source
already reads; nothing else is asked of the daemon.

- **Container.** The header is the name, the state word of D407 with its tone
  (running and healthy `good`, starting and restarting `busy`, unhealthy and
  failed `bad`, paused `warning`, stopped and created `neutral`) and the image
  as a link. Sections: **Overview** — id, created, started or finished, exit
  code, restart policy and count, command and entrypoint as `code`, working
  directory, user, the Compose project and service as links to their level;
  **Health** — the status, failing streak and the last checks as a table, when
  a health check is defined; **Network** — published ports as a table, and the
  networks with each address, as links; **Storage** — mounts as a table, a
  volume as a link; **Environment** — pairs, sensitive by name (D421);
  **Labels** — pairs, collapsed; **Resources** — memory and CPU limits, `empty`
  when unlimited. A notice when it restarted more than three times, or was
  killed for memory (`OOMKilled`).
- **Image.** Tags as a list, id, size, created, architecture and system,
  entrypoint and command, exposed ports, environment, labels, and the number
  of layers linking to its History view; the containers using it as a table
  of links.
- **Volume.** Driver, mount point, scope, created, options and labels, and the
  containers mounting it as links.
- **Network.** Driver, scope, internal, the subnets and gateways, and the
  containers on it with their addresses, as links.
- **What changed is told.** A view tab is told by the watch of D414 when the
  daemon reports an event about its container, image, volume or network, and
  reads itself again, as a level does now.

## Where it is written down

D419–D421 in a new architecture file, `docs/architecture/sources/views.md`,
because `content.md` is at 28 KB of its 32; D422 in
[sources/docker.md](../architecture/sources/docker.md). The renderer and its
blocks are added to the `/ui-kit` showcase with every block and every value
kind, which the kit's test already demands of a component in `shared/ui`
(*checked*: the blocks read the generated client's types, which the kit
does not import, so they live in `features/content/view/` and the showcase
draws them from there; the state word with its tone is the kit's
`AppStateTag`; a moment and a size reuse the formatting screens already
share).

## Slices

1. **The contract and the container.** `DocumentView` and the `view` kind,
   `ViewPanel` with every block and value kind and the button to the JSON,
   the way back from the tree, the showcase; Docker's container view. Tests:
   the model refuses an unknown block or value kind; the container view from
   recorded inspects (running, healthy, failed with an exit code, no health
   check, a sensitive variable); the client renders each block (unit) and the
   container opens on its view and switches to JSON (browser).
2. **Image, volume, network, and live views.** The other three views; a view
   tab told by D414's events.
3. **Other sources, one at a time when wanted** — none is promised here. The
   likely first ones: a Kafka topic's configuration, an S3 object's metadata,
   a ZooKeeper node's stat and ACL.

## Not planned

- **A view edited in place.** A view is read only; a document is edited
  where it is edited now (D48, D295).
- **Views defined by a person** — choosing fields, saving a layout. The
  source decides what its document means.
- **Charts inside a view.** Metrics have dashboards (D125).
