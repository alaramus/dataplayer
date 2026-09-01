# Sharing a view

Date: 2026-09-01. Settles roadmap phase 2, and D58, D59, D60, D61.

Sources read: `myquasar/src/myapp/components/CopyPaste/`,
`myquasar/src/myapp/stores/contentCopyRegister.ts`,
`dbwebtool/webdb/webapi/view_services/fetch_data_handler.py`,
`dbwebtool/webdb/webapi/view_services/execute_data_handler.py`, and the grant
machinery already in `backend/app/connectors/routes.py`.

## What the old application had

Nothing to port. The sources the roadmap named as evidence turn out to be a
clipboard, not a sharing feature: `contentCopyRegister.ts` is an in-process
object of `any` values keyed by `kind` and `name`, and the CopyPaste panel moves
those values between screens of one browser tab. It never leaves the session,
never names a recipient and never touches permissions. A search of both old
projects for a share link finds none.

So this round is designed from the goal rather than from a precedent.

## The goal, as stated by the user

Press Share on a table, get a link, send it to a colleague. If they already
have the connection, the link takes them straight to the same table with the
same filters. If they do not, they either were given access as the link was
made, or they ask for it from the screen the link lands on. Email delivery
comes later.

## The plan this replaces

The roadmap's phase 2 was an immutable snapshot: re-fetch the bounded page at
creation, store the rows with an owner, a token, an expiry and a revocation,
and show the recipient a read-only copy. It is a coherent feature and it is not
this one. A snapshot answers "the recipient must not be given the connection";
here the recipient is a colleague who works with the same database, and a
frozen copy would only go stale in their hands.

The snapshot is therefore moved to the deferred list with that reason written
down, not deleted. When a recipient who must not hold a grant appears, it is
the right design for them.

## The decision that shapes everything else: the link is an address

Two things are called sharing and they are not the same: naming what I am
looking at, and deciding whether you may look at it. The old application mixed
them, and every product that mixes them ends up with a URL that is a password.

DataPlayer already answers the second question. D33 is a grant of an ordered
level on a connection, resolved by one funnel that every data route must state
a requirement for. So the link answers only the first question and stays out of
the second. This is D58.

What it buys:

- creating a link is harmless, so it needs no permission of its own beyond
  being able to read the thing;
- a forwarded link cannot spread access, because it never carried any;
- revocation has exactly one meaning — remove the grant — and does not have to
  chase down what a link already handed out;
- the reader's own level governs what they can do in the shared view, so a
  colleague with `write` edits, and nobody has to explain why the same table
  behaves differently when reached two ways.

**Rejected: the capability link**, which grants on redemption. It is the common
shape in consumer products and it is wrong here. The moment a link grants, it
is a credential in a chat window; the funnel D33 built stops being the only way
in; and "who has access to this database" can no longer be answered by reading
the grants table.

**Rejected for now: node-scoped grants.** The honest reading of "share this
table" is access to that table alone, and DataPlayer cannot express it: a grant
names a connection, the catalog is not filtered by anything finer, and a node
id belongs to the source and changes when the source renames it. Introducing a
second dimension of access inside a Share button is how leaky permission models
are born. Instead the dialog states plainly that the level covers the whole
connection. If node-level access is wanted, it is its own round, with the
catalog and the funnel in scope.

## What is stored, and why each field is there

The record (D59) is deliberately small.

**The token** is 128 random bits in base64url. Not a UUID: a UUID in an address
reads as an internal id and invites people to try the next one. Not hashed: a
hash defends against somebody reading the database, and that reader already has
the grants themselves and the encrypted credentials, while the token by itself
opens nothing. It will appear in proxy logs as part of a path, which is
acceptable for the same reason.

**The body** is a discriminated union on `kind`, and only `rows` exists today.
It carries the filters, the sorting, the column order, visibility and widths,
and the page size — everything the sender is looking at except the page number.
The page is dropped on purpose: under a filter the reader's page three holds
different rows, so a shared offset points somewhere else, while the query means
the same thing on both screens.

The body is a typed model rather than opaque JSON because it crosses a
boundary, and this project's rule is that what crosses a boundary has a type.
It is also already described once — in zod, in `grid/persist.ts` — so typing it
on the server means the shape is stated in the contract and generated into the
client, instead of being written a second time by hand and drifting.

**The captured names** of the connection and the node exist for one screen: the
reader without a grant. That screen cannot ask the source anything, and a
request for access that says only "somebody shared something" is not answerable.
They are as they were at creation; the owner, who can read the source, sees the
current name.

**No expiry.** Expiry protects a link that carries rights. This one does not,
so ageing it out only breaks the address in a ticket six months later. Deletion
stays, as tidying: the author removes their own, the owner of the connection
removes any made to it. Both are cascaded away with the connection and with the
author's account.

**Deduplication** by author, connection, node and a fingerprint of the body, so
pressing the button twice does not mint a second address for one view.

**The open log** is one row per reader with a first and last time. It answers
"did it reach them", so the author's own opens are not written into it. An
author who has lost their grant loses the log with it: the link keeps working
for the people it was sent to, but somebody whose access was revoked should not
retain a window onto who reads that connection.

## Resolving a link: a state, not an error

D60. The route answers 200 with `open` or `no_access`, and keeps 404 for a
token that does not exist or was deleted — both answered the same way so the
space of tokens cannot be probed.

"No access" is the expected half of this feature, not a failure. Answering it
with 403 and a body would make the client read an error for information it is
going to render as a normal screen.

This is a deviation from D33's rule that no access answers 404, and it is
written down as one in `sharing.md`. The reasoning: the 404 there exists so
that connector ids cannot be used to enumerate other people's connections. A
token is not enumerable, and the person holding it was told what it was when
they were sent it. Refusing to name the connection would leave them asking for
access to an unnamed thing.

The client side is mostly reuse. `revealInCatalog(connectorId, nodeId, label)`
already exists, the workspace already restores its own layout, and
`prunedToColumns` already removes filters and sorts naming columns that are
gone. What is new: the router guard has to remember where somebody was going
before it sent them to the login screen, the landing page has to explain a node
that no longer exists or a connection that is switched off, and an already-open
tab is focused and told the sent query rather than duplicated, because tabs are
one per connection and node.

## Asking for access

D61. The request is durable because the alternative — a notification fired at
whoever happens to be connected — loses the ask when the owner is offline, and
the person who asked has no way to know that.

It always asks for `read`. A person who cannot see a connection is not in a
position to choose a level on it, and the owner picks one when answering.
Approving is nothing but writing an ordinary grant: this feature adds a way to
ask, not a second kind of access.

Declining is told, without a reason. Silence does not spare anybody — the
person presses the link again and asks again — and a reason field turns a human
conversation into a form.

The request hangs off the connection rather than the link, so deleting a link
does not silently withdraw an ask the owner has already seen. The link is kept
beside it as context and cleared when it goes.

Both notifications ride one topic of the `shares` module, per user, on the
existing socket. A general notification bus would be a product decision of its
own — what accumulates, what counts as read, what survives a reload — and two
messages do not justify taking it. The notification leads to the access dialog
of that connection, where grants are given anyway; there is no inbox screen,
which at this volume would be an empty page somebody has to remember to open.

Nothing opens by itself when a request is approved. The person is working on
something else; a tab appearing under their hands is not a courtesy.

## Where the code goes

A new module `app.shares`, placed between `app.system` and `app.connectors` in
the layer contract, so it may use connections, users and the socket while
nothing below it learns about sharing.

The D33 funnel moves out of the private `_get_or_404` in
`connectors/routes.py` into `connectors/access.py`, and both modules call it.
Copying the check into the new module would have produced two rules that agree
today and diverge on the first change — and a divergence in an access check is
a hole, not a style difference.

On the frontend, `features/shares/` with the dialog, the landing page and the
code that applies a resolved link to the workspace; the route `/s/:token`; the
button in the grid tab's header beside download. The existing connector
`ShareDialog` grows the link and request sections rather than being duplicated,
because the owner's actual sequence is one: copy the link, add the colleague.

## Delivery, in two stages

1. The record, the token, creation and resolution, the landing page, opening
   into the workspace, deletion, the open log, and grants given from the same
   dialog. This closes the main scenario: give access, send the address.
2. The request: the row, the state machine, the topic, the owner's answer, and
   the notifications on both sides.

One spec, because a request without a link has no way to reach anybody, and the
decision about it is made here.

## What the tests have to cover

Backend: creating a link requires `read` and nothing more; resolving one
answers `open`, `no_access` and 404 in the three cases; a deleted connection
takes its links and requests with it; deduplication returns the same token; the
open log excludes the author and is refused to an author whose grant is gone;
a request is not created when a grant exists, is not duplicated while open, and
approving it writes exactly the grant D33 defines; a token appears nowhere in
an error message; and the extracted funnel still refuses a foreign connection
with 404 and an insufficient level with 403.

Frontend: the union of resolved answers renders three different screens; a
shared query with a dropped column is pruned and reported; a body of an unknown
`kind` is refused politely.

End to end: the colleague pattern in `frontend/tests/sharing.spec.ts` already
creates a second account and signs in as it. One scenario for stage 1 — owner
shares, grants, colleague opens the link and sees the sender's filters — and
one for stage 2 — colleague opens without a grant, asks, owner approves from
the notification, colleague opens the view.
