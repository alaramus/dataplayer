# Dropping several relations at once

## Goal

Tick three tables and drop them. Until now `drop_relation` declared
`bulk = False`, so the menu greyed itself out the moment a second node was
ticked, and clearing out a schema meant opening the same dialog once per
relation.

## Why it was not simply `bulk = True`

`bulk` means "one filled form may be applied to a set", and the transport
behind it is the same request repeated once per node. That is right for files:
five deletions are five independent facts, a refusal of one says nothing about
the other four, and what did land stays landed.

It is wrong for relations, and the reason is dependencies. Ticking a table and
the view over it and sending two requests refuses the table — the view is still
there when the first request runs — unless the client happens to send them in
the lucky order. The user did not ask for two drops in an order; they asked for
one drop of two things.

So the set becomes the subject:

- `bulk` keeps its meaning and says only that a set is allowed;
- a new capability `TakesNodeSet` says the whole selection arrives in one
  request, and `PreviewsSet` says that one request can be rehearsed;
- both are `runtime_checkable` Protocols, and `ActionInfo` derives `takes_set`
  and `previews_set` with `isinstance`, exactly as it already derives
  `takes_file`, `previews` and `downloads` — a flag and an implementation can
  disagree, an isinstance check cannot.

Two routes carry it: `POST …/actions/{name}/set` and
`POST …/actions/{name}/set/preview`, both taking `{node_ids, params}`. A
separate body rather than a second optional field on `ActionRequest`: they are
different requests, and a body where exactly one of two fields must be filled
has to be argued about at every call site. An action that does not take a set
answers 415 rather than quietly acting on the first node in the list.

Applicability is unchanged: the set route resolves the action through the same
`_action_for_nodes` the download route uses, so every node is checked exactly
as it is for a single request, and a duplicate in the list is refused.

## How PostgreSQL drops a set

One statement per kind of relation, each naming every target of that kind, all
inside one transaction:

```sql
DROP VIEW s.a, s.b;
DROP MATERIALIZED VIEW s.c;
DROP TABLE s.d, s.e;
```

Grouping is what makes the set work: everything named in one `DROP` is already
gone when the server checks what depends on the rest of it, so a table and the
view over it go together without a cascade. Views are dropped before tables for
the same reason, one level up.

One transaction, so a selection that cannot go whole leaves every relation in
it standing. Half a drop is not a partial success; it is a schema nobody asked
for.

The preview is still the drop, rolled back — `PostgresSession.rehearse` now
takes several statements and runs them in the order they will really run in,
inside the transaction it discards. A preview that rehearsed the statements
separately would be an answer to a different question.

## What the user sees

The menu enables Drop as soon as every ticked node admits it. The dialog shows
one preview of the whole selection, in the server's own words, and one
confirmation. The message afterwards names one relation by its name and several
by their count: five names in a toast is a list nobody reads, and the catalog is
about to show which ones went.

## Rejected alternatives

- **`bulk = True` and nothing else.** Order-dependent refusals, and a partial
  drop reported as a success with footnotes.
- **Ordering the client's requests by dependency.** That is `pg_depend` restated
  in TypeScript, in the worst possible place.
- **Always cascading.** The whole point of the preview is that a cascade is a
  decision.
- **One preview per node, stitched together in the dialog.** Nothing on the
  client knows what to call each answer, and separately rehearsed statements do
  not describe what the one transaction would do.

## Deferred

Other actions that would be better as a set — moving several relations into one
schema is the obvious one — keep the repeated transport until somebody wants
them; the capability is there when they do.
