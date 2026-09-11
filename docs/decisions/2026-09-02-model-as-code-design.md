# The model a source published, written as code

## Goal

Three things the old application had, and one question about them.

`sqlalchemy_description` and `django_description` turned one table into an ORM
class. `dbdiagram` did something else entirely despite the name: it built a
laid-out graph for the old front end to draw, which is a diagram engine rather
than a model for dbdiagram.io. The question asked here was whether there is a
better way to get the model into that service.

There is, and it is the service's own language: DBML. A text document, pasted
into dbdiagram.io, which draws it — no layout algorithm to own, no graph to
keep in step with a renderer.

## Decision

One action, three dialects: SQLAlchemy, Django and DBML.

The renderers are pure functions over `RelationModel`. A source that can
describe a relation already publishes its columns, their types, its keys, its
comments (D22), so writing that out is a transformation of an answer the
source already gives — no connection, no SQL, no second description. They live
in `adapters/model_code.py` rather than in one driver, which is where the old
application had two copies of them, each reading a driver-shaped dictionary.

Offered on a schema as well as on a relation, and the schema is the useful
case: a diagram of one table is a rectangle, and a diagram of a schema is the
thing people draw. A selected schema stands for its contents.

## A download may ask something first

`ProducesDownload` took only the selection. A dialect is not a selection, so
the capability now takes the filled form as well — `download(node_ids, raw)` —
and validates it with the action's own model, exactly as `perform` does.

The signed ticket that a browser redeems carries the parameters with it. It is
the authority for one invocation, and what was chosen is part of what was
authorised; putting it in the URL instead would make it something a person
could edit on the way.

On the client it does not end in a file. The action declares
`x-ui-workflow: model-as-code`, and a screen of its own opens instead of the
generic form:

- the three dialects as three names on one line, because the whole choice fits
  there and a menu to pick one of three is a click that buys nothing;
- the document itself, read-only, in the editor everything else in this
  application reads code in;
- Copy, Save, and — for the one dialect a website draws — a door to that
  website. Save is the bytes already on the screen, so nothing is asked twice.

The words for the three, and which one the screen opens on, are read off the
schema: `x-ui-choices` carries the source's own label per value, and the
field's default is the dialect shown first. A download with nothing to ask and
nothing to show still runs straight from the menu.

## What the generated code says about itself

None of it claims to be a migration, and each file says so in its first line.
The reasons are worth stating:

- **No singularisation.** `order_items` becomes `OrderItems`, not `OrderItem`.
  A singular is a guess about English, and a guess in generated code is a bug
  somebody has to find.
- **Django models are `managed = False`.** These tables exist and Django did
  not make them.
- **A composite primary key is named as what it is.** Django has none, so the
  columns stay ordinary fields and `unique_together` says the rest — under the
  names the file actually gave them, which for a key column is the reference
  rather than the column.
- **DBML writes a `Ref` only between tables in the document.** A reference to
  something outside it makes dbdiagram refuse the whole file.
- **A type is read whole.** `timestamp with time zone` starts with the letters
  `time` and is not a time; `interval` is a span and not a moment. Both were
  wrong until the generated file was read.
- **A key points at a relation by its published name**, looked up in the
  document, never by taking a node id apart (D21).

## Rejected alternatives

- **A graph with coordinates, like the old `dbdiagram`.** That is a layout
  engine to own and keep in step with a renderer, to produce something
  dbdiagram.io already does better from text.
- **A content representation per dialect.** Three new representation kinds and
  three new content models to show a file that is meant to leave the
  application anyway.
- **Rendering on the client from `RelationModel`.** The same computation in two
  places is a defect, and this one would be three.

## Deferred

Alembic, Liquibase, Prisma and plain DDL; a diagram drawn in the application;
and choosing which relations of a schema to include beyond ticking them.
