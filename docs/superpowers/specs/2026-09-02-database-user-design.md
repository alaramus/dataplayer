# A database user

## Goal

The last item of phase 3.5, and the one operation of the old application that
was written down and then deliberately left out when the PostgreSQL inventory
was made: `create_database_user`. The old implementation is four lines —

    CREATE USER {} WITH PASSWORD '{}'
    GRANT CONNECT ON DATABASE {} TO {}

— with every one of the four values formatted into the string by
`str.format`, and a form that asked for a user, a password and a database from
a list. The inventory refused to port it as it stood, for two separate
reasons, and both are still true. This slice answers them rather than
overrules them.

## What the inventory objected to, and what changed

> `create_database_user`: left out — a password through a statement is D2c's
> exact prohibition, and roles are a server-administration surface, not a data
> surface.

**The first objection is about who may do it.** It is answered by the level,
not by leaving the operation out. When it was written, `own` was on the access
scale because routes compared against it, and no action had ever asked for it:
every action wanted `read`, `write` or `structure`, and `structure` is the most
that can be handed to somebody else. So an action requiring `own` is exactly
the statement the objection wanted — this can be done by the person whose
connection it is and by nobody they shared it with — and it costs no new
mechanism, because `_allowed_or_403` already asks every action what it needs.

**The second objection is about the password.** It is half right, and the half
that is right is not the half it names. D2c forbids building a query from
client strings; it does not forbid a value from a client reaching the server,
which every filter and every edited cell does through a placeholder. What is
true here is that a placeholder is not available: PostgreSQL takes no parameters
in a DDL statement, so `CREATE ROLE … PASSWORD $1` is not a statement at all.

The distinction that matters is therefore not "bound or formatted" but "quoted
by the driver or quoted by hand". `psycopg.sql.Literal` is the driver's own
quoting of a Python value — the same code that turns a bound parameter into
bytes on the wire, run before the statement is sent rather than by the server —
and it is what `sql.Identifier` already is for names. A password containing a
quote, a backslash and a semicolon comes out as one literal, and the test that
proves it does not read the statement: it signs in as the new role with that
exact password.

## What is offered

One action, `create_role`, on the Roles report — the report that already lists
every role the server has, written for D55. Extensions are changed from the
report that lists extensions for the same reason: the place a person goes to
see what there is, is the place to make one.

The form has three fields and no more:

| Field | Why |
| --- | --- |
| Name | Validated as a name, then composed with `sql.Identifier` |
| Password | `SecretStr`, 8–128 — the bounds the application's own accounts use |
| May connect to this database | `GRANT CONNECT`, on the database the connection is on |

The database is not a field. The old form asked for one from a list, and the
answer is always the database this connection is already on: asking is offering
a way to grant a privilege somewhere the person is not looking. It is asked of
the server as `current_database()`, so the identifier that reaches the
statement is one the server spelled.

Everything else a `CREATE ROLE` can say — `CREATEDB`, `CREATEROLE`,
`SUPERUSER`, `IN ROLE`, `VALID UNTIL`, `CONNECTION LIMIT` — is left out. The
first three are ways of handing out more than the person filling in the form
holds, and the rest are not what "make a user" means to anybody who asks for
one. What the new role may read is granted with SQL, in a console somebody has
deliberately taken out of read-only (D66); that is a decision about somebody
else's tables, and a form with a schema picker in it would be a worse way to
make it.

## Why nothing is previewed

Every other command on a report can be asked what it would do first. This one
cannot, and the reason is what a preview is: the statement run inside a
transaction that is rolled back, kept for the sake of the server's own words
about it (D46). Those words are the value; a rehearsal that returned nothing
would be a slow way to learn what the form already says. And a statement
carrying a password is exactly the statement whose driver text must not be
passed on, so what is left to show is nothing.

The refusals a person actually meets are answered before anything is sent:

- a name beginning with `pg_` is the server's reserved prefix, refused here so
  that nothing is attempted with a password in it;
- a name that is taken is a conflict, the same shape a taken folder name and an
  installed extension answer with;
- a password shorter than the bound is refused by the model, before `run`.

What is left goes through `session.transaction`, which maps a SQLSTATE to this
module's own sentence and passes on no driver text — `42501` when the
connection may not create roles, `42710` when somebody took the name in
between, `28P01` when the server holds a password policy of its own. The test
for that path is not a mock: it makes a role, connects as it, and asks it to
make another one.

## Both statements, or neither

`CREATE ROLE` and `GRANT CONNECT` run in one transaction. A role that exists
but was not granted what the form promised is worse than no role: the form said
what it would do, and half of it is a thing somebody has to notice.

## Known deviation worth naming here

`log_statement = 'ddl'` makes PostgreSQL write every DDL statement to its own
log, and this one carries a password. The way to close that is to send a
pre-computed SCRAM verifier instead of the password, which is what `psql`'s
`\password` does.

It is not done here, and the reason is not effort. A verifier decides on the
server's behalf which authentication method the new role can use: a server
configured for `md5` stores what it is given, and a role that holds a SCRAM
verifier cannot authenticate against a client or a server expecting the other.
Sending the password lets the server apply its own `password_encryption`, which
is the only answer that is right on every server this application may be
pointed at. Closing the log exposure properly means reading
`password_encryption` first and computing the verifier the server would have
computed — a slice of its own, and one that should arrive with a test that
signs in on a server configured each way.

## Decision

**D79. Making a user of the server is the owner's, and its password is a
literal.** The statement, its consequences and the known deviations are in
[the actions contract](../../architecture/sources/actions.md).

## What it took

- `adapters/postgres/roles.py` — the action, its refusals and its two
  statements.
- `adapters/postgres/names.py` — the name rule the relation, schema and role
  forms share. It was written twice already; a third copy is what the rule
  against copying with edits is about.
- `REPORT_COMMANDS` in `adapters/postgres/actions.py` — which report admits
  which command, a table now that two of them do rather than a comparison
  against one id.
- Nothing on the client. The form is the generic one, and it draws a masked
  field because Pydantic renders `SecretStr` as `format: password`, which
  `jsonSchema.ts` has mapped to a password field since the first connector
  window. An action that asks for a secret needed no new part of the form —
  which is the whole point of a source-declared vocabulary.
