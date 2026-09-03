# A key space, walked and written

## Goal

Redis arrived as a source type that could only be reached. That was honest
while the phase it arrived in was about starting containers, and it stopped
being useful the moment somebody started one: a connection that answers "yes,
I am here" and nothing else is a connection nobody opens twice.

This is the rest of it — browsing keys, reading what they hold, writing one,
deleting one, and working with expiry — which is the whole of what people do
to a key space by hand.

## The tree is already in the names

Redis has no schemas and no tables. What it has is a flat set of names, and by
universal convention those names are written with colons: `session:42:token`,
`cache:user:7`, `queue:jobs`. Every tool that shows a key space shows that as
a tree, because the structure is not invented by the tool — it is what the
names were given when somebody chose them.

So the catalog groups by the separator. The top lists the first segment of
every key as a branch, and opening one lists the next. It is not configurable:
a source type whose tree shape is an option is a type with two behaviours to
explain, and there is no second convention to support.

A key whose name has no colon in it is a key at that level, beside the
branches. And a key called `user` and a branch called `user:` are different
things that exist at once, which is why the two kinds of id are marked apart —
`k:` and `f:`. Without the mark, a listing of the key and a listing of the
branch above it would be the same request.

## A key is a kind of its own

It was tempting to call a key a `table`: it is read as rows and it has a size.
That is exactly the mistake `BaseNode` warns about — the old application's
`schema` field held a PostgreSQL schema name for one source and the literal
string "directory" for another. A key has a Redis data type and an expiry
clock, and every action that names a table would have been offered on it.

So `KeyNode` joins the union, with the friction that is meant to come with
that: the compiler asked the frontend for an icon, a role and a caption in the
same commit.

The namespace above it is a `directory`, and that one is not a compromise: a
container of nodes with nothing else to say about itself is what a namespace
is.

## Nothing runs KEYS

`KEYS *` blocks the server for the length of its own scan, which on a real key
space is a production incident. Everything here is `SCAN`, which exists so
that a client cannot do that, and the cursor is followed until it returns to
zero or a ceiling is reached.

The ceiling is the honest part. A key space of ten million names has no useful
tree, and a page that tried to draw one would fail slowly rather than quickly.
Five thousand keys is where it stops. What is beyond that is a deviation, and
it is recorded as one.

The type, the expiry and the size of every key in a listing are read in one
pipeline rather than three round trips each.

## What a key holds

Read as rows, and the shape follows the type: a hash is fields and values, a
list is positions and values, a sorted set is members and scores, a string is
one value. One reader per type in a table, so a type that gains one is a line.

A list and a sorted set page in the server, because those two carry an order.
A hash and a set are read whole and sliced here, which is a deviation and is
recorded as one.

Nothing sorts and nothing filters, and the columns say so. Redis has no index
over values, so a grid that offered either would be offering something this
source would have to fake by reading everything.

## Four actions

Write one, take one away, give one a deadline, take the deadline off. That is
what a person does to a key space by hand; the rest arrives from whatever
writes it.

Writing covers changing a value too: a name already in use is refused unless
the form says to replace it, which makes "write this" one action instead of a
create and an update that would differ only in their refusals. Strings only —
a hash or a list built from a form would be a form with a repeating group in
it.

Two things came out of this that are not about Redis at all.

**A form field may be optional.** An expiry is `int | None`, which Pydantic
writes as two branches with the bounds inside the one that is not null. The
form reader had never met one and threw, so a nullable field is now an
ordinary field with `required: false` — which is what it is.

**A destructive action may word its own question.** Everything destructive
until now removed what it named, so the dialog wrote "are you sure you want to
delete this" itself. Setting an expiry is destructive — it schedules the key
ceasing to exist — and it is not a deletion. Only the action knows the
difference, so the action says it.

## Shown as a tree, not as a folder

The first version presented the key space the way a file source is presented:
a level at a time, with a path across the top and a folder to walk into. It
worked and it was wrong. A namespace is not a directory — nothing lives *in*
it, the name is simply longer — and walking down four levels to read one field
of one hash is four round trips and four screens to get back from.

So a source now says which of the two shapes its catalog wants, and a key
space says `tree`. Declared on the type rather than branched on by name: a
screen asking "is this Redis" is the thing D62 exists to stop.

Expanding a branch asks the catalog for its children; expanding a leaf asks
for a page of what it holds, and the rows of that page become rows of the same
tree — one column is a list of values, two are a name and a value, more are
written out. Nothing in that mapping knows what Redis is, which is what lets
the next source that wants a tree have one.

It is the same tab, not a second kind of panel. Everything the head offers — a
path, a grouping filter, a search — belongs to a level and is not drawn; the
actions menu is fed from the one selected node instead of from a set of ticks,
and is otherwise the same menu answering the same question of the server.

Opening a key properly is still a tab: the tree shows the first fifty of what
a key holds and says so when there are more, and the grid is where paging and
the full value live.

## An address, written and read back

The form gained the connection string PostgreSQL has had since D15, for the
same reason: a person who has a `redis://` line wants to paste it rather than
take it apart into four fields, and a person looking at a connection wants the
line back.

There is no library call to lean on. redis-py parses a URL and will not write
one, so the grammar is stated once in `adapters/redis/url.py` and the tests
exercise both directions against each other. A `rediss://` address is
recognised and refused: this source has no TLS options, and a scheme quietly
read as plaintext would be worse than a sentence.

## How it was verified

Twenty-one tests against a real Redis rather than a fake: what they are about
is what the driver does to one, and a fake would be this repository's own idea
of Redis checked against itself. Development gets one from compose and CI gets
one as a service, on database 15, emptied around every test.

Then in the browser: a key space of a hundred and ten sample keys walked as a
tree, a hash expanded in place to show its three fields, a string and a hash
opened as rows in a tab, a key written with an expiry and found again in the
catalog, its expiry moved and then removed, and the key deleted. And the
address: composed into the connection form, and a pasted one taken apart back
into the host, the port, the database and the password.

## Decision

**D91. A key space is a catalog, grouped by the separator its names already
use.** The statement, its consequences and the known deviations are in
[the source contract](../../architecture/sources/contract.md).

## What is not here

A query console — Redis has commands, not statements, and one that accepted
them would be a shell on somebody's server. Editing a hash field in place.
Writing anything but a string. Watching a key space change. And a way to reach
past the scan ceiling by typing a pattern.
