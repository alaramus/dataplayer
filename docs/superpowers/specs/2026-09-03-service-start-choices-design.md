# Choosing what a started service is made with

Supersedes the second half of
[Two ways to start a service, and what comes back](2026-09-03-service-start-modes-design.md),
which established the two modes (D88), the password shown once (D89) and the
filled database (D90). The two modes and the filled database stand. What
changes here is what the chosen mode may decide, and what happens to the
password afterwards.

## Goal

The form with questions in it asked four of them, and the two that mattered
were missing. Somebody who starts a database to use it from their own tools
needs to know its password and, often, which port it is on — and the first
version answered both with "the server decides, and it will tell you once".

Four things, which are one thing: a chosen start may name the port and the
password; a Redis may be asked to want no password at all; nobody is asked any
more whether the service should be reachable from the machine, because the
answer was always yes; and the window that says where a service listens stops
being a one-time reveal, because once the password is out of it there is
nothing left to ration.

## The password was the whole knot

D88 refused a chosen password for a real reason: it would have to survive the
gap between the request that carried it and the job that starts the container,
and the only encrypted home this application had for a service's password was
the connector the service becomes (D4). Writing it anywhere else meant either
a second encrypted home or an unencrypted one.

The reason held. The conclusion — never let anybody choose — turned out to cost
more than it saved: every started database had a password known to nothing but
this application, so the port published on the machine could be reached by
nobody. The demonstration worked and the tool did not.

So there is a second home, and it is bounded on every side that can be
bounded:

- **Encrypted, under the connector key.** It is a connector secret that has
  not reached its connector yet; a key of its own would be a second thing to
  rotate for no gain.
- **On the service row, not in the job.** A job row is not encrypted, and
  `parameters` is deliberately for things that are not secret. The row is also
  what a retry is planned from, so the password survives a retry the way the
  role and the database do.
- **Erased when the connector exists.** `_save_connector` nulls it in the same
  commit that writes the connector id. A finished service has one home for its
  password again.
- **Never in the JSON column beside it.** `chosen_credentials` is readable by
  anything that can read the table, and it stays that way precisely so that
  nothing in it has to be treated as a secret.

The window that used to reveal a password is the other half of this. It showed
one thing worth protecting and, because of it, could be opened once — so the
address and the names, which are not secret at all, were rationed too, and a
person who closed the window lost them. Now nothing secret is in the answer:
the password is shown in neither mode, and a person who needs to know one
types it when they start the service. What that costs is written down as a
deviation: a password this server made up cannot be recovered.

### Where a bad password is refused

Pydantic's `pattern` on a `SecretStr` field cannot be used, and the reason is
worth stating because it is not obvious: a failed constraint puts the value it
rejected into the validation error, and FastAPI returns that error verbatim.
A 422 body echoing somebody's password is exactly what `SecretStr` exists to
prevent. So the shape of a usable password is checked beside the other
refusals about a password, and the answer names the rule rather than the
value.

## Three shapes, not a nullable string

How the password is decided has three answers — made up here, this one, none
at all — and they are a discriminated union for the reason the start modes
themselves are: a nullable string plus a boolean has a fourth combination that
means nothing, and something would eventually have to decide what it meant.

"None at all" is not a property of the request but of the template. Running
Redis without `--requirepass` changes the command, leaves the environment
empty and makes the connector authenticate by a different word; those three
vary together, so they are one value — a `Shape` — and a template carries the
one it takes when it is asked to run unprotected. A template with no such
shape refuses the request. A PostgreSQL that trusts every connection is not
something this server will start, and saying so is better than quietly making
a password up instead.

Which slots are settled at all is then read off the shape rather than listed:
an unprotected Redis names no credential anywhere, so none is settled, so no
secret is generated. The alternative — generate one and leave it out of the
container — is how a password ends up in a log with nothing using it.

## The port, and the choice that was not one

A port on the host is the only number about a container a request may now
carry, and it does not weaken D80: it changes where the container is published
and nothing about what runs. Zero is the default and means the runtime picks,
which is right for everybody without a reason to care; a number is somebody
who will point a configuration file at it. A port already taken is a refusal
from the daemon rather than a silent move to another one — this application
still never binds a socket to find out what is free.

"Reachable from this machine" went the other way. It was a checkbox with one
sensible answer: a service nobody can open in their own tools is one they
start again with the box ticked. It is gone from the request, and every
service is published on the loopback address.

## The bug this also fixes

`connector_id` on a service row is nulled when its connector is deleted — the
foreign key says `ON DELETE SET NULL`, deliberately, because deleting a
connection is not deleting a service. But every screen and the retry route
read "no connector" as "the creation never got that far". So deleting the
connection of a working database made the services window call it "no
connection yet" and offer to start it over, and starting over begins by
removing the container and its volume.

The row now stamps when it became a connection. The two empty cases are
different facts and are now told apart by different fields: `connector_id` is
what it has, `connected_at` is what it had.

## Removing a service, and the connection it made

D84 kept the two deletions apart in both directions, and the half that read
badly was this one: removing a service left a connection to a database that no
longer exists, which works for nobody and which the person removing the
service almost always wants gone. It is now asked in the same confirmation,
ticked by default, and the answer travels as a flag on the request.

The connector goes in the route rather than in the job, through the same
deletion a connection removed from its own screen takes — cached pool
invalidation included. Deleting a row of this application is not minutes of
work to watch, and the container is the only part that is.

## What was removed

`ComposesSecretUrl` and its two implementations. Its docstring said it had
exactly one caller — the window that revealed a service's password — and that
caller is gone. A helper whose only job is to put a password into a string,
kept with nothing calling it, is the most dangerous kind of dead code there
is. The address the window shows is now composed by `draft_connection_string`,
which is the one that builds from loose values and leaves the password out;
reading a pasted URL that carries a password is unaffected, because tools
people paste from still write them.
