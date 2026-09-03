# A second service, and the first source that only connects

## Goal

The sixth item of phase 4: add a Redis pilot, once the lifecycle is right for
PostgreSQL. The roadmap orders it that way deliberately — a second template
before the first one worked would have been two half-built things — and its
value is exactly that Redis is not shaped like PostgreSQL.

## What the second one exposed

**A password that is not an environment variable.** The official Redis image
has no variable for one: it is told on the command line, `redis-server
--requirepass …`. The template's `command` was a tuple of strings, which could
not express that, and the two wrong ways out were obvious — let the client
send a command (D80 exists to forbid exactly that), or write the password into
the template (a constant secret is not a secret).

So a command is written as values, like the environment: `Fixed("redis-server")`,
`Fixed("--requirepass")`, `PASSWORD`, resolved once per service. Twelve lines
of change, and the registry stopped being PostgreSQL-shaped.

**A template that uses one credential and no others.** Redis has no user and
no database name. `credentials` holds a password alone, and the slots a
template never mentions are absent rather than empty — which the existing test
over the whole registry already required and now actually exercises.

**A service whose adapter cannot read anything.** A ready service becomes a
connector (D83), and a connector needs a source type. Redis is now one, and it
implements `check_connection` and nothing else.

## A source type that only connects

`DataAdapter` asks for one method. Everything else — browsing, reading rows,
actions, content — is a separate protocol a driver may implement, and the
catalog derives what a type can do from the driver rather than from a list
(D2, D9). So a Redis adapter with one method is not a stub: it is a source
type that can be reached and not read, and the screen says so in the words it
already had for that case — "This type only checks that it can reach the
source".

Its options are a discriminated union, password or none, for the reason
PostgreSQL's are (D16). A single model with `password: SecretStr | None` would
be worse twice over: a form that asks half its users for something to leave
empty, and a field D4's secret split would not recognise, because it matches
the exact annotation.

The `redis` client is contained by a contract of its own, beside the ones for
`psycopg` and the file-format libraries.

## How it was verified

Eight tests for the adapter — that it is registered, that it claims no
capability it does not have, that an unreachable server is a `network` answer
whose message names no host, that the password is a secret of the schema, and
that the two ways of connecting are two shapes. The whole registry's tests now
run over two templates rather than one.

Then the real thing, through the API against the daemon: `redis:8` pulled and
started with `--requirepass`, the readiness probe authenticating through the
adapter, "Redis is ready", the connector saved and checking ok in 1 ms, and
its own log lines read back. Opening the connection in the browser shows the
catalog saying it cannot be browsed, which is the honest answer.

## Decision

**D85. The second service is what proves the first one was not a shape.** The
statement, its consequences and the known deviations are in
[managed services](../../architecture/services.md).

## What is not here

Reading a key space. What Redis holds — keys, types, sizes, a scan — is a
source contract of its own, and it belongs to the phase that adds adapter
families deliberately rather than to the phase about running services.
