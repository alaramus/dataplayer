# Sharing a connection: grants, levels and what an administrator is

## Problem

A connection belongs to exactly one user and is reachable by nobody else. Two
things follow that the application now needs and cannot express.

A team looks at one database. Today the only way to let a second person see it
is to hand over the credentials, which puts them outside the encrypted column
and outside the application entirely.

Editing landed before any of this. Cell update, row insert, bulk delete and
column DDL are live, and there is no level below "everything": the moment a
connection can be shared at all, sharing it means sharing `DROP COLUMN`.

The resolution point is still narrow — `crud.get(..., owner=user)` behind
`_get_or_404`, 24 call sites in one file. Every feature added widens it.

## The grant

A grant is a row: connector, user, level. Nothing else. Not a role, not a
policy, not a rule that has to be evaluated — the question "may this user do
this to this connection" is answered by a primary key lookup.

Levels are ordered, and the order is the whole semantics:

| Level | What it admits |
| --- | --- |
| `read` | catalog, relation model, rows, node path, page download, a connection check |
| `write` | plus changing rows: cell update, insert, bulk delete |
| `structure` | plus changing shape: add, drop, rename a column, a column default, renaming a relation |
| `own` | plus the connection itself: its options, its credentials, its grants, deleting it |

`own` is on the same scale but is not grantable. An owner is not a user with a
strong grant; ownership is a column on the connector, and the scale exists so
that one comparison answers every route. A grant carries one of the other
three.

Three levels rather than two because DDL is already implemented and is
irreversible in a way a cell edit is not. Adding the level later would not be a
new value in an enum — it would silently redefine every grant already issued.

## Where it is enforced

One funnel, and it is not optional. `_get_or_404` and `_adapter_for` take
`requires` as a required argument, so a route added later cannot reach a source
without stating what it needs; mypy refuses the call otherwise. There is no
default, because a default is the thing that gets forgotten.

Two statuses, and the difference is what the caller already knows:

- no access at all — **404**, the same answer as a connector that does not
  exist. Otherwise the id space is an oracle for which connections others hold.
- access below what the route needs — **403**. The caller can already see this
  connection; hiding it now would only be confusing.

An action declares its own level the way it declares `destructive`, on the
class. File actions — new folder, rename, delete, upload — are `write`:
in a file source the node is the data, and there is no shape to change
separately. `rename_relation` is `structure`. The default is `write`, so an
action that says nothing is not thereby free.

Listing the actions of a node filters by what the caller may do, rather than
offering what running would refuse. Same rule as D2d: the answer states what is
possible, and the client never derives it.

## Corrected during execution: 401 is not 403

The client signed a user out on 401 **or** 403, and the backend answered 403
for a token it would not accept. Both were reasonable while no route ever
refused a level: 403 could only mean "this token is no good".

The first grant makes them collide. A colleague pressing something their level
does not admit gets a 403 — and would have been thrown out of the application
by it. So authentication now answers 401 with `WWW-Authenticate: Bearer`, which
is what the two statuses have always meant, and the client signs a user out on
401 alone. An account switched off mid-session answers 401 too, for the same
reason: the session it is holding is over.

This was found by an end-to-end scenario and not by any unit test, because
every part of it was individually correct.

## What the answer says

`ConnectorPublic` gains `access` and, when the connection is not the caller's
own, the owner's email. A screen hides what it must not offer by reading the
level, not by knowing the rules. Without this the grid would have to render an
editable cell and learn about the refusal from a 403.

The list of connections is what the caller owns plus what has been granted to
them. So is the set the health monitor watches: a shared connection with no dot
would be a connection whose state is permanently unknown.

## An administrator

`is_superuser` currently bypasses the owner check, which means every list a
superuser opens contains everyone's connections and every data route is open to
them. That is replaced by a narrower rule: **an administrator has rights over
accounts, not over data.** Creating, deactivating and deleting users stays
theirs. Reading somebody's rows requires a grant like anyone else's.

This is not a theoretical tidy-up. The credentials in a connector are
encrypted precisely so that holding the database does not mean holding the
sources; an unconditional bypass gives back through the API what the encryption
was protecting.

## Consequences left as they are

- A file connector's root stays the **owner's** personal directory. Sharing one
  is sharing that directory, at the granted level. D8 is unchanged: the
  connector still cannot leave the directory it was created against.
- A page download is written to the **caller's** own storage, which is already
  what the route does.
- Cache keys already carry the caller's id, so two people sharing a connection
  do not share cache entries. A little duplicated work, no leak; not worth a
  wider key.

## Not in this round

- **Groups.** The old application had them. A grant is resolved through one
  function, so a second source of grants is an addition there and not a change
  to any route.
- **An access log.** The old application recorded who opened what. It is a
  separate concern with a separate retention question.
- **Public links and API keys.** Sharing with a person who has no account is a
  different mechanism; this one is about people who have one.

## Rejected alternatives

- **A permission string per route, checked by a decorator.** The set of
  permissions grows with the number of routes, and nothing keeps the two in
  step. An ordered level is four values that never grow.
- **Grants on a catalog node rather than a connection.** A node id is opaque
  and belongs to the source; a grant that names one would break when the source
  renames it, and the client would need to understand ids to ask about them.
- **Copying the connector row per grantee.** The credentials would then exist
  in as many encrypted copies as there are readers, and rotating them would
  mean finding all of them.
