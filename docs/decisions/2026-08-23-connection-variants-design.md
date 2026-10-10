# Connection variants: the authentication method and parsing a connection string

Date: 2026-08-23
Status: done
Subproject: 7-preparation, the second of two

## For someone starting from a clean session

Read in this order: [AGENTS.md](../../AGENTS.md), decisions R1–R15;
[ENGINEERING.md](../../ENGINEERING.md) in full; the spec of the previous
subproject `2026-08-23-connector-window-design.md`. This subproject is its
direct continuation and the last of "7-preparation".

What is already done and what is relied on here:

- The connection window is floating, several of them at once
  (`features/connectors/ConnectorWindow.vue`, engine `shared/windows/`).
- The form is built from the JSON Schema returned by `GET /adapter-types/`
  (`shared/SchemaForm/jsonSchema.ts` → `SchemaFields.vue`).
- A field itself says which tab it is in and whom it shares a row with
  (`app/adapters/layout.py` → `json_schema_extra`).
- The connection string is assembled by the server and **only shown**:
  `SupportsConnectionString`, route `POST /connectors/describe-draft`, a
  source without that capability answers 501.

Three commands that will be needed right away:

```bash
docker compose up -d --build backend
```

```bash
bash scripts/generate-client.sh
```

```bash
cd backend && uv run pytest tests/ -q
```

## Goal

The connection window now always has one set of fields: host, port, database,
user, password. The set of fields needs to depend on the chosen connection
method, and a pasted connection string needs to be split into the fields
rather than typed in again.

This is the last part of the window rework: the previous one gave the window
itself and the layout, this one — what changes in it.

## What is not here

**The connection string does not become a second stored form of the options.**
A pasted DSN is parsed on the server and spread over the fields; the fields
stay the truth, there is one stored form. A real "URL only" mode, as in the
reference, is rejected, for two reasons at once:

- a DSN may contain a password, so by R4 it becomes a `SecretStr` as a whole
  and goes into the encrypted blob. A secret is not returned — when editing a
  connection the field would come back empty, and to change one port one would
  have to type the whole DSN again;
- it is a second stored form **on top of** the authentication variants, that
  is, a multiplication: "fields + password", "fields without password", "URL +
  password", "URL without password". Four forms for two independent questions,
  and with a third question — eight.

The mechanism is not lost: a source that really has no component parts — a
REST endpoint, a queue at an address — declares one `url` field and needs no
variant.

**SSL certificates are not added.** A third method would require storing and
encrypting files and handing them to the driver; that is separate work.

## Decisions

### V1. A variant is a discriminated union on the server

The options model stops being one class and becomes a union by the field
`auth_method`:

```python
class _PostgresBase(BaseModel):
    host: str = Field(title="Host", json_schema_extra=layout(row="address"))
    port: int = Field(default=5432, title="Port", json_schema_extra=layout(row="address"))
    database: str = Field(title="Database", json_schema_extra=layout())

class PostgresUserPassword(_PostgresBase):
    model_config = ConfigDict(title="User & Password")
    auth_method: Literal["user_password"] = "user_password"
    user: str = Field(title="User", json_schema_extra=layout())
    password: SecretStr = Field(title="Password", json_schema_extra=layout())

class PostgresNoAuth(_PostgresBase):
    model_config = ConfigDict(title="No auth")
    auth_method: Literal["no_auth"] = "no_auth"
    user: str = Field(title="User", json_schema_extra=layout())

PostgresOptions = Annotated[
    PostgresUserPassword | PostgresNoAuth, Field(discriminator="auth_method")
]
```

**A flat union, not a nested one.** Common fields are inherited from a base
class, not moved into a sub-object `auth: {...}`. Nesting would change the
stored form (`config` would become two-level), and with it the separation of
secrets, which today cuts by top-level names (`service.split_options`). A flat
union keeps `config` flat: exactly one key, `auth_method`, is added.

**Two methods, not one.** A drop-down of one item is a stage prop, and
`no_auth` is not invented: `trust` and `peer` do occur in `pg_hba.conf`, and the
difference in the driver is honest (the password is simply not passed in
`conninfo`).

`model_config = ConfigDict(title=...)` is not decoration: the class title gets
into `$defs` and becomes the label of the item in the list. Without it the item
would be the class name.

### V2. The registry stops requiring `type[BaseModel]`

`AdapterType.options_schema` is typed today as `type[BaseModel]`, and a union
is an `Annotated[Union[...]]`, which has no `model_json_schema`.

`app/adapters/options.py` appears — one seam through which everyone reaches the
options schema, whatever it is:

```python
type OptionsSchema = Any   # type[BaseModel] or a discriminated union

def json_schema(schema: OptionsSchema) -> dict[str, Any]: ...
def validate(schema: OptionsSchema, data: Mapping[str, Any]) -> BaseModel: ...
def variants(schema: OptionsSchema) -> list[type[BaseModel]]: ...
def secret_field_names(schema: OptionsSchema) -> set[str]: ...
```

Inside is a `TypeAdapter`, which works the same with an ordinary model and with
a union: verified, `TypeAdapter(Union).json_schema()` returns
`{$defs, discriminator, oneOf}`, and `TypeAdapter(Model).json_schema()` an
ordinary schema.

`registry.secret_field_names` **moves here** and starts computing the union of
names across all variants. This is the very place where R4 is either kept or
quietly broken: a field declared `SecretStr` in only one variant must get into
the encrypted blob.

Consumers to be moved over: `connectors/service.py`
(`split_options`, `fill_missing_secrets`, `build_adapter`),
`adapters/routes.py` (`options_schema.model_json_schema()`),
`adapters/registry.py`.

### V3. Existing connections require a data migration

Verified: Pydantic **rejects** an object without the discriminator field
(`union_tag_not_found`). So already saved postgres connections will stop being
readable, and with that — being opened, checked and polled.

One alembic revision, data only, no schema change. The table is called
`connector` (verified), the column `config` is jsonb:

```sql
UPDATE connector
SET config = jsonb_set(config, '{auth_method}', '"user_password"')
WHERE adapter_type = 'postgres' AND NOT (config ? 'auth_method')
```

The downgrade removes the key. `user_password`, not `no_auth`: all existing
connections have a password, otherwise they would not have been saved.

Forgetting this migration means getting not a validation error at startup but
connections that stopped opening; so its test is written before the variant
code.

### V4. The driver gets what is chosen and keeps quiet about the rest

`PostgresSession.__init__` takes the union. `conninfo()` passes `password`
only when the variant carries it:

```python
if isinstance(self._options, PostgresUserPassword):
    parts["password"] = self._options.password.get_secret_value()
```

This is the only place in the driver that knows about variants.
`connection_string()` (O8 of the previous subproject) already contains no
password, so it does not need to change.

**Check by hand that `no_auth` really works:** the `db` container in
`compose.override.yml` starts with a password, so a passwordless connection to
it must **not** succeed and must report `auth`. A test of a successful `no_auth`
requires a server with `trust`, and there is none in this subproject — record it
in the deviations.

### V5. Parsing a connection string is a capability of the class, not of an instance

An adapter cannot be built while there are no options, and parsing is exactly
what produces them. So the question is asked of the **type**, just like
`action_types()` in R13:

```python
@runtime_checkable
class ParsesConnectionString(Protocol):
    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]: ...
```

Route `POST /connectors/parse-url`, body `{adapter_type, url}`, response
`{options: {...}}`. A source without the capability — 501, an unparseable
string — 422. No connection is opened.

For PostgreSQL the inside is `psycopg.conninfo.conninfo_to_dict`, verified:
`postgresql://ann@db:6543/app` → `{'user': 'ann', 'dbname': 'app',
'host': 'db', 'port': '6543'}`. Hence three details, each of which would
otherwise become a bug:

- the key is called `dbname`, and the field `database`;
- `port` arrives as a **string**;
- `password` is absent when it is not in the string.

**The driver returns a complete and valid set of options, including the
discriminator.** If the string has a password — `user_password`, if not —
`no_auth`. The inference belongs to the driver, not the form: a form that
guesses the authentication method by the presence of a substring is the
`isFieldShowing` of the old application, where it all started.

A caveat that has to be told to the user in the interface: a string without a
password gives "without password", and if the password simply was not meant to
be written into the URL, the method has to be switched by hand.

**A password in the response is not a disclosure.** The client has just sent
this very string. But it must not get into the log.

### V6. The form reads `oneOf` and merges what is common

Verified: Pydantic returns the schema of a union like this —

```json
{ "$defs": { "PostgresNoAuth": {...}, "PostgresUserPassword": {...} },
  "discriminator": { "propertyName": "auth_method",
                     "mapping": { "no_auth": "#/$defs/PostgresNoAuth", ... } },
  "oneOf": [ { "$ref": "#/$defs/PostgresUserPassword" }, ... ] }
```

**`schemaToFields` does not resolve references today** — it reads
`schema.properties` and that is all. This is the first thing that will have to
be done.

A pure function `readSchema(schema)` appears in `jsonSchema.ts`, returning a
tagged union:

```ts
type SchemaShape =
  | { kind: "plain"; fields: FieldSpec[] }
  | { kind: "variants"
      discriminator: FieldSpec        // select, choices = mapping items
      common: FieldSpec[]             // fields identical in all variants
      byVariant: Record<string, FieldSpec[]> }
```

`common` are the fields that occur in **all** variants with the same kind and
title, in the order of the first variant. This is what keeps host and port
from jumping when the method is switched: the common ones are drawn once and in
place, and only the variant's own fields change.

The order on screen: common → choice of method → variant fields. In the
reference Authentication stands between port and user, and the database below
the password; here the database ends up above the choice of method. The
divergence is deliberate: the only way to match is to give a field an explicit
ordinal, and that is a third layout coordinate for the sake of one row.

Accompanying edits, each one needed:

- `FieldSpec.choices` is now `string[]`, and an item needs both a code and a
  label (`no_auth` → "No auth"). It becomes `{ value: string; label: string }[]`;
  `AppSelect` already handles objects — check.
- `jsonSchemaToZod` builds validation from **the common fields plus the active
  variant**, not from the whole union.
- `defaultValues` fills the discriminator with the first item of `mapping`.
- Switching the method must not erase common values.

### V7. A button that parses a pasted string

> **Changed during execution.** There is no "paste" button: the string is typed
> directly into the field. See "What turned out differently" at the end.


The connection string stays display-only, but next to the "copy" button a
second one appears — "paste and parse": it takes text from the clipboard, sends
it to `parse-url` and replaces the form's values with the response.

Not an editable field, because a field that sometimes shows the assembled value
and sometimes accepts typed input has to answer the question "which of the two
is the truth right now", and we have one answer: the fields are the truth.

## What changes

### Backend

```
app/adapters/
├── options.py        new: json_schema / validate / variants /
│                     secret_field_names on top of TypeAdapter
├── protocol.py       + ParsesConnectionString (classmethod, issubclass)
├── registry.py       options_schema: OptionsSchema; secret_field_names moves out
├── routes.py         the schema is taken through options.json_schema
└── postgres/
    ├── options.py    union by auth_method, two variants
    ├── session.py    password only for the variant that carries it
    └── adapter.py    + options_from_url (classmethod)
app/connectors/
├── service.py        split_options / fill_missing_secrets / build_adapter
│                     through app.adapters.options
└── routes.py         + POST /parse-url
app/alembic/versions/ one revision: auth_method for existing connections
```

### Frontend

```
frontend/src/
├── shared/SchemaForm/
│   ├── jsonSchema.ts    readSchema, resolving $ref, choices as pairs
│   └── SchemaFields.vue unchanged — gets a ready list of fields
└── features/connectors/
    ├── ConnectorWindow.vue  choice of method, common fields, variant fields,
    │                        "paste and parse" button
    └── api.ts               useParseUrl
```

## Order of work

Each step is a failing test, then code. The order is not accidental: the first
two are not visible on screen, but everything else stands on them.

1. **`app/adapters/options.py`** and moving all consumers to it. Behaviour does
   not change: the schema is still one model. Green `pytest`, `mypy`,
   `lint-imports`.
2. **Data migration** (V3) and its test.
3. **The union in `postgres/options.py`** (V1) and `session.py` (V4). Here the
   test "the password is not sent with `no_auth`" must fail and gain meaning.
4. **`parse-url`** (V5): 501 for the file source, 422 on garbage, parsing with a
   password and without.
5. `bash scripts/generate-client.sh` — otherwise the frontend will see neither
   `oneOf` nor the new route.
6. **`readSchema`** (V6) with tests on resolving `$ref`, merging common fields
   and order.
7. **The window**: choice of method, the parse button.
8. **Playwright scenarios** — switching the method on screen, pasting a string.

## What holds it

| Check | What it catches |
| --- | --- |
| `pytest tests/adapters/test_options.py` | `secret_field_names` across the union; `json_schema` for a model and for a union |
| `pytest tests/adapters/test_postgres.py` | `no_auth` does not pass the password into `conninfo`; `user_password` does |
| `pytest tests/connectors/test_service.py` | `split_options` puts the password into the blob for one variant and nothing for the other |
| `pytest tests/connectors/test_parse_routes.py` | 501 without the capability, 422 on garbage, `dbname`→`database`, port as a number, inferring the method |
| migration | a connection saved before it is readable after it |
| `bun run test:unit` | `readSchema`: `$ref`, common fields, order, code-label pairs |
| `bunx playwright test` | changing the method removes the password and keeps the host; pasting a string fills the fields |

Separately — what a unit test will not prove: **the tab strip has never yet
been visible** (both types have one group). If PostgreSQL gets a second group
in this subproject, check it in the browser; if not, leave the deviation as it
is.

## Known deviations this will add

- **`no_auth` is not verified against a server that accepts it.** The `db`
  container requires a password, so the test proves only that the password is
  not sent, not that a connection without it works.
- **Parsing a string guesses the method.** A URL without a password gives
  `no_auth`, even if the password simply was not meant to be written into the
  string.
- ~~**The order of fields differs from the reference.**~~ Removed. The order is
  set by the server itself — by the declaration of fields — and the form no
  longer overrides it in any way: the class base holds only the address, each
  variant declares the method right below it. A field still has no explicit
  ordinal, and a field that needs to stand between two fields of its own model
  will require one.
- ~~**Switching the method loses the values of fields that are not in the new
  variant.**~~ Not confirmed during execution. The values live in one flat
  record, and the variant only decides what is drawn and what is sent — so a
  password typed before switching to `no_auth` comes back on screen, and is not
  sent to the server with `no_auth`.
- **The parsed string goes into the request body.** The password from a pasted
  DSN passes through the server and returns to the client; nothing new is
  disclosed, but it must not get into the logs, and there is no check for this.
- **There are two variants, and both belong to one type.** The mechanism is
  designed for a union of any width, but verified on the narrowest possible.

## What turned out differently than planned

Recorded here, not only in code: a plan that diverged from execution is fixed
together with the code.

- **The discriminator got a `title` and `layout()`.** In V1 it is declared as a
  bare `Literal`. Then the field label would have become "Auth Method", and the
  choice would have had nowhere to inherit a tab from; the form reads the title
  and layout from the property of the first variant itself, so the server stays
  the only place where anything is named.
- **`parse-url` does not check completeness.** What could be parsed is
  returned, plus the discriminator; a string without a user is common, and a
  refusal on it would be worse than an empty field. Only what psycopg cannot
  read at all, what names no host and what names an unusable port is rejected.
- **`readSchema` treats non-adjacent fields as common too.** `user` is declared
  in both variants after the discriminator and matches by kind and title — so it
  is drawn once together with the other common fields. Hence the divergence
  from the reference in order, now by two fields rather than one.
- **`AppIconButton` learned `loading`.** Bypassing the kit through pass-through
  attributes is already recorded in the deviations.
- **The URL field is editable, the "paste" button is removed** (V7 revised).
  The objection from V7 — "which of the two truths right now" — is removed not
  by a prohibition but by the field not keeping an answer of its own: what is
  typed goes to the driver, the driver produces fields, the fields assemble the
  string back. A password typed in the string ends up in the password field and
  disappears from the string; the rule is visible rather than explained. While
  the cursor is in the field, the assembled string is not written into it: any
  prefix of an address parses as an address, and otherwise a slow typist would
  have the string rewritten under the cursor — this is verified by a scenario
  that failed before the fix.
- **The `<hidden>` placeholder comes back on leaving the field** if nothing was
  typed: a field that was entered and left has changed nothing.
