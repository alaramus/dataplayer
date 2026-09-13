# Sharing a view

The Share button on a tab, the link it produces, and how a person without
access asks for it. Read this before changing the share record, the link route
or the access request.

Grants on a connection are D33 in [backend.md](backend.md); this file never
redefines them. A dashboard is shared by grants of its own and linked by its
address, D129 in [dashboards.md](dashboards.md). The tab whose address is shared is in
[workspace.md](workspace.md), and the grid state that travels in the link is
D24 in [grid.md](grid.md).

Decisions here: D58, D59, D60, D61.

## What exists today

A grid tab has a Share command next to its download command. It opens one
floating window, like every other transient form opened from a tab (D14), so
the link and the grid it was made from are looked at together rather than one
covering the other. Everybody who can reach the connection sees the link to
this view and who has opened it; the owner of the connection also sees who
holds a grant, who is waiting for one, and every link made to that connection.
A connection's own window answers the same questions on its Permissions
page — who holds a level, who is waiting — and the dialog opens from there
with the adding half alone, so the two are never on screen at once.

An empty recipient picker distinguishes no other active accounts from all
available accounts already holding grants. The first points to an administrator
and reopening Share; the second points to the connection's Permissions tab.
These explanations appear only after the directory and grants load successfully.
A failed read instead offers Retry and disables giving access until both reads
are available again.

Opening a link signs the reader in if needed, then reveals the node in the
catalog and opens the tab with the filters, sorting, column layout and page
size the sender saw. A reader without a grant gets a card naming who shared
what, and a button that asks the owner for access. The owner hears about the
ask wherever they are working and answers it beside the grants, on the
connection's Permissions page; the person waiting is told, and if the answer
was yes the link they are holding opens in front of them.

```
backend/app/shares/
├── models.py     the share record, the open log, the request, and the API
├── view.py       the body of a shared view, and what makes two views the same
├── crud.py       lookup by token, deduplication, the open log, the request
├── topic.py      the socket topic: a request arrived, a request was answered
└── routes.py     create, resolve, list, delete; ask, approve, decline, cancel

backend/app/connectors/
└── access.py     the D33 funnel, used by connectors and by shares alike

frontend/src/features/shares/
├── api.ts               vue-query around the generated client
├── sharedView.ts        a grid's state as a link carries it, and back
├── intent.ts            a resolved link waiting for the workspace to open it
├── requests.ts          the socket topic, and the wording of what it carries
├── ShareDialog.vue      the link, who has access, who is waiting, other links
└── ShareLandingPage.vue the /s/:token screen
```

Four places outside that feature take part: the Share command in the grid's
header, `openShared` in the workspace page — which reveals the node, opens the
tab and leaves the view where the tab takes it — the workspace again, which
hosts the dialog a notification opens, and the router, whose guard now
remembers where somebody was going before it sent them to sign in.

## D58. A share link is an address, not a permission

A link names a place: a connection, a node, and the view over it. It carries no
rights. Who may read what stays D33 — a grant on the connection, held by the
reader's own account — and the link changes nothing about it.

Four consequences, and they are the point of the decision:

- Anyone holding `read` or better may create a link, because creating one hands
  over nothing.
- A reader holding `write` may edit in a shared view, because their level says
  so. The link neither raises nor lowers a level.
- There is no public link and no signed-out reader.
- Access is closed by revoking the grant. Deleting a link does not close
  anything, and the dialog says so in words.

**Rejected: a link that grants access when it is opened.** Then the link is a
credential. Forwarding it spreads access, "revoke the link" has to answer what
it already handed out, and rights arrive through a URL in a chat as well as
through the funnel D33 built. One enforcement point stops being one.

**Known limit, stated in the dialog.** A grant covers the connection, so
sharing a table shares the database at that level. The dialog names the
connection, not only the table, before the owner presses anything. Node-scoped
access is a different contract — the catalog would have to be filtered, and a
node id belongs to the source — and a button is not the place to introduce it.

Spec: [Sharing a view](../decisions/2026-09-01-shared-view-links-design.md)

## D59. A shared view is a stored record with a typed body

The link is `/s/<token>`, where the token is 128 random bits in base64url under
a unique index, stored as it is. It is not hashed: hashing defends against a
reader of the database, and that reader already holds the grants and the
encrypted secrets, while the token opens nothing on its own.

The record carries the author, the connection, the node, the body of the view,
and the names of the connection and the node **as they were when it was
created**. The names are copied because the screen shown to a reader without a
grant cannot ask the source what anything is called.

The body is a discriminated union on `kind` with `extra="forbid"`. The first
and only variant is `rows`: filters, sorting, column order, column visibility,
column widths and page size. The page number is not carried — under a filter
the reader's page three is not the sender's, and the shared meaning is the
query, not the scroll position.

A format change that breaks reading is a new `kind`, never a version field: a
version field becomes a chain of `if version ==`, which is the branching this
project replaces with types. Optional fields are added in place. A record that
no longer validates answers that it was made by an earlier version of the
application, and does not fail as a server error.

No expiry. Ageing out a link protects nothing, because the link gives nothing,
and it breaks an address left in a ticket. The author deletes their own links;
the owner of the connection deletes any link made to it, as tidying rather than
as defence. A record goes when its connection or its author's account goes.

Pressing Share twice on the same view returns the same record and the same URL,
matched on author, connection, node and a fingerprint of the body. Otherwise a
button pressed twice leaves two addresses for one thing.

Opens are recorded once per reader — first time, last time, count — and the
author's own opens are not recorded, because the question the log answers is
"did it reach them". A log is not visible to an author who has lost access to
the connection; the record survives, the window into who reads the connection
does not.

Spec: [Sharing a view](../decisions/2026-09-01-shared-view-links-design.md)

## D60. Opening a link answers with a state, not a status

Resolving a token answers 200 with a discriminated union. `open` carries the
connection, the node and the body. `no_access` carries who shared it, the
copied names, and whether this reader already has a request waiting. 404 is
kept for a token that does not exist or was deleted, and the two are answered
identically so a token cannot be probed.

Having no access is a normal outcome of this route — the request flow exists
for it — not a failure, and a client that had to read it out of an error body
would be reading an exception for information.

**Deliberate deviation from D33.** There, no access answers 404 precisely so
the id space cannot be used to discover whose connections exist. Here the
holder of a token is told the name of a connection they cannot read. The token
is unguessable, the sender named the thing when they sent it, and a request for
access that cannot say what it is about is not a request anybody can answer.

What the client does with a resolved link:

- signed out, it goes to the login screen and returns to the same link
  afterwards;
- with access, the node is revealed in the catalog and the tab opens carrying
  the sender's query; columns the relation no longer has are pruned by the same
  function that prunes a query restored from storage, and the reader is told;
- if that tab is already open, it is focused, the sent query is applied, and a
  notice says so — a tab is one per connection and node;
- the URL is replaced with `/` once the link has been applied, so a reload does
  not open the tab a second time;
- a node that no longer exists, and a connection that is switched off, are
  explained on the landing screen instead of failing inside a fresh tab, where
  the error would look like a broken link rather than a changed source.

Spec: [Sharing a view](../decisions/2026-09-01-shared-view-links-design.md)

## D61. Access is asked for as a durable request, answered by an ordinary grant

A request is a row: connection, requester, the link it came from, and a state.
It always asks for `read`; somebody who cannot yet see a connection is not in a
position to ask for `structure`, and the owner chooses the level when they
answer.

Approving writes the grant D33 already defines and nothing else — there is no
second kind of access with its own rules. Declining closes the request and
tells the requester, without a reason: the reason is a conversation between
people, not a field in a form.

The rest of the state machine is small and deliberate. A second request while
one is open is not a second row. No request is created when a grant already
exists. The requester may cancel their own. A closed request does not block
asking again later, because a grant can be revoked and circumstances change.

The request belongs to the connection, not to the link: rights live on the
connection, and deleting a link would otherwise silently withdraw a request the
owner had already been told about. The link is kept beside the request as
context — "came through Maxim's link" — and is cleared when that link goes.

Both sides hear through one topic of this module, per user, on the socket D18
describes: the owner that a request arrived, the requester that it was answered.
The notification leads to that connection's own window, open on the page
where grants are given anyway. There is no inbox screen, and nothing opens by itself while
somebody is working.

A connection is invisible without a grant, so a request can only ever arrive
through a link. That is the whole discovery mechanism, and it is why the link
and the request are one feature.

Spec: [Sharing a view](../decisions/2026-09-01-shared-view-links-design.md)

## What the dialog has to say out loud

Two sentences are load-bearing and are not left to the reader to infer:

- when a level is given from this dialog, that it covers the whole connection,
  named, and not only the table the link points at;
- when a link is deleted, that this does not take anybody's access away, and
  what does.

Both restate decisions above, in the place where somebody is about to act.
