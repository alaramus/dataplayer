# Two ways to start a service, and what comes back

## Goal

Three things asked for together, which turn out to be one: a service can be
started with no questions at all or with a few; a service started that way is
worth looking at rather than empty; and the password the server made up is
shown to the person who now owns it.

They are one because each is unusable without the others. A one-button start
that produces an empty database demonstrates nothing. A filled database nobody
can open from their own tools is a demonstration behind glass. And a password
nobody is ever told is a database only this application can use — which was
the honest answer while nothing was published, and stops being it the moment
something is.

## Two shapes, not one shape with everything optional

The obvious design is a request with nullable fields: leave them out and the
server decides. It reads badly in both directions. A reader of the model
cannot tell what a half-filled one means, and a client "asks automatically" by
failing to say things, which is not a thing a protocol should let you do by
omission.

So the request carries a discriminated union. `AutomaticStart` has no fields
at all — the whole of it is the word "automatic" — and `ChosenStart` has the
short list of what is a person's to decide. Both forbid unknown keys, which
restates D80 exactly where a client can reach it: a request naming an image, a
command, a volume or a port number does not validate, and there is a test that
walks all five.

The automatic start does not even take the name. Somebody who has not been
asked for one has not got one in mind, and the server calls it what it is and
which one of them it is: "PostgreSQL 1", then "PostgreSQL 2".

## What a person may choose

The connection's name, the role and the database to create inside the server,
whether it is reachable from the machine, and whether to fill it. That is the
list.

Which credentials may be named is the template's to say, not the request's:
`choosable` is a closed set per template, and a value for a slot it did not
open is refused rather than dropped. A Redis server has no role and no named
database, so somebody who typed one has made a mistake worth being told about.

The password is deliberately not on the list. It could have been — a person
setting up a demo may well want a password they already know — but a chosen
one has to survive the gap between the request and the job that uses it, and
the only place this application encrypts anything is the connector a service
becomes (D4). Putting a password on the service row would be a second
encrypted home, or worse, an unencrypted one. The password stays the server's,
and the answer to "then how do I know it" is the third part of this slice.

## The port is the runtime's answer

Publishing was refused in the phase that built services, on the grounds that
opening a port on the machine is a separate decision. It is that decision,
made: bound to `127.0.0.1` and nowhere else, so "from outside" means from the
machine this server runs on.

Which port is not a request's to name, and not this application's either. It
would have to bind a socket to find out what is free and then race whoever
took it in between. Docker picks — an empty `HostPort` means "pick one" — and
the create job reads back what it picked off the container. So `Placement`
carries a boolean where it used to carry a number, and `ContainerStatus` gained
the number.

## Shown once

A stamp on the row, not a flag: `credentials_shown_at` is when, and "has it
been shown" is derived from it. The route reads the password out of the
connector through the adapter's own options model — a `SecretStr` there is
what says which field is secret — and refuses the second ask.

The address it gives is not the one the connector holds. That is a container
name on a network only this server is on; what a person needs is `127.0.0.1`
and the published port. A service started without one says why there is no
address rather than showing one that would fail.

Only an automatic start opens the window by itself. Somebody who filled in a
form knows what they asked for; somebody who pressed one button has been told
nothing. Until it has been shown, the services window offers it.

## Filling it

The project already has a schema worth exploring: the one it develops against.
Enums, domains, composite types, generated columns, arrays, ranges,
partitions, a few hundred rows — written to exercise this application's type
handling, which is exactly what makes it worth walking through.

It used to be two files at the repository root, mounted into the development
prestart container and deliberately kept out of the image. That reasoning was
about sample data in a deployment's own database, and it still holds; what
changed is that filling a database is now something the application does at a
person's request. So the files moved next to the driver that runs them, and
`seed_database.py` reads them from there: one copy, two callers.

Running it is a capability — `SupportsSampleData` — for the reason every other
one is. A source that cannot be filled is skipped rather than refused: the
person asked for a database, and this is the part of the answer Redis cannot
give. And it goes through a seam beside the readiness probe, so the create job
is still exercisable with nothing running.

## How it was verified

Fourteen tests through the routes: that an automatic start names itself and
counts, that it publishes and fills, that a chosen one uses the names it was
given and may refuse both extras, that a password field is refused, that a
name the template did not open is refused with a sentence, that a name which
is not a name is refused, that nothing about the container can be asked for,
that the port comes from the runtime and is written down, and that the
credentials are shown once and then refused.

Then the real thing: a PostgreSQL started automatically against the actual
Docker daemon, its sample schema browsed in the catalog, and its published
port opened with `psql` from outside the application using the password the
window showed.

## Decisions

**D88. Two ways to ask for a service, and neither of them names a container.**
**D89. A generated password is shown once, where it becomes useful.**
**D90. An empty database demonstrates nothing, so an automatic start fills
one.** The statements, their consequences and the known deviations are in
[managed services](../architecture/services.md).

## What is not here

A chosen password. A choice of what sample data goes in. A reveal that can be
asked for twice. And a published port reachable from another machine — that is
a tunnel, and it belongs to whoever runs the server rather than to this.
