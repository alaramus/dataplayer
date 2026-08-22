# DataPlayer — engineering rules

How code is written in this project. Normative whenever you touch code,
whatever the task. What the project is and where it is going: [AGENTS.md](AGENTS.md).

**A rule without a check is a wish.** So every rule below says what holds it up.
Two markers, and confusing them defeats the point:

- **Enforced:** — holds today. The named command can be run right now and fails
  on a violation.
- **Will be enforced:** — no check yet. The future one is named, and until it
  exists the rule rests on review alone.

Promising a check that does not exist is the worst thing that can be done to
this document: its whole value is that **Enforced** can be taken on faith.

Every contract listed as enforced was verified by deliberately breaking it and
watching it fail. A contract that has never gone red proves nothing — the
dependency rule below was stated for three sub-projects and was already being
violated by the time a check was added.

---

## Layers and dependencies

- One module, one responsibility. Dependencies point inward:
  `api → system → connectors → adapters → users → core`, and `core` depends on
  nothing else in the application.
- Extension is a new module plus registration, not edits rippling through
  existing ones. A new source type is a new package under `adapters/`.
- A third-party driver SDK stays in the adapter that owns it. `psycopg` is
  imported by `adapters/postgres/` and by nothing else, so a driver upgrade has
  one place to change.
- Application assembly happens in one place per surface (`api/main.py`);
  dependencies are passed in rather than reached for through module globals.

**Enforced:** `uv run lint-imports` — three contracts in `backend/.importlinter`:
layer order, `core` importing nothing from the application, and the driver SDK
staying inside its adapter. All three were checked by introducing a violation.

## Types

- `mypy --strict` over `backend/app`. Settings live in `pyproject.toml` so the
  requirement does not drift with tool defaults.
- Data crossing a boundary is a Pydantic model, not a `dict[str, Any]`. Bare
  dictionaries with string keys do not travel between layers.
- A closed set of values is a `Literal` union, and a set of shapes is a
  discriminated union — so a forgotten case fails to compile or fails to
  validate rather than passing silently.
- A suppression carries a reason. `# type: ignore` without one is a defect.

**Enforced:** `uv run mypy app` and `uv run ruff check app tests`. The union
shapes additionally reject unknown keys at runtime: `CatalogNode` sets
`extra="forbid"`, and there is a test that a field belonging to one kind is not
accepted on another.

## Polymorphism over branching

- Registries and protocols instead of `if adapter_type == ...` chains. Two
  `elif` branches on a type is the signal to write a class or a registry entry.
- A capability is a `runtime_checkable` Protocol, and a route checks for it.
  An adapter that lacks one answers 501 rather than implementing a stub.

**Enforced:** by tests that a source without a capability answers 501, for
catalog, fetch and actions. An action is reachable only through the registry
that holds it: a test asks the API for a method of the driver by name and
expects 404. The absence of `elif` chains rests on review.

## Reuse and abstraction

- Look before writing. Similar code in two places is a reason to extract, not
  to copy with edits.
- Generalise on the second or third use, not in advance. Speculative
  abstraction costs as much as duplication.
- The same computation in the backend and the frontend is a defect: it belongs
  on the server and arrives in the response. The catalog's row estimate is
  reused by the grid rather than recomputed.
- Duplication left in place deliberately carries a comment saying why.

**Review only.** Machines do not help here; the third similar thing in a diff
is where to look.

## Queries and untrusted input

This is the section the old application failed hardest, so it is stated
separately from general typing.

- **A query is never built from client strings.** Filters are a closed set of
  predicates; a raw SQL fragment from a client is not accepted anywhere.
- **Identifiers are validated against the source before a statement is built.**
  A column name is checked against the relation's actual columns, then passed
  through `psycopg.sql.Identifier`. Values always go through placeholders.
- **Paging has a ceiling.** `limit` has a default and a maximum; there is no
  "unlimited".
- **Driver text never reaches the caller.** Adapter errors are reduced to a
  kind and a safe message; driver messages carry the connection string,
  password included.

- **A path from a client is judged by one containment rule.** A file source
  resolves every path against its root and refuses anything that lands outside,
  symlinks followed; a path segment must be a plain name by the rules of both
  platforms, so a Windows drive reference is refused rather than silently
  dropped by a join. The root itself is never named by a client. A name typed
  into a form and the filename inside a multipart upload are the same kind of
  string and go through the same rule — there is no second one.

**Enforced:** ruff `S608` flags SQL built by string formatting; tests attempt
injection through a column name and through an operator and expect rejection;
a regression test asserts the password does not appear in an error message.
Path containment is covered by tests for `..`, for an absolute path, for a
drive-bearing segment and for a symlink out of the root, in the adapter and
through the API.

## Asynchrony

- The backend is async throughout: the application is network-I/O bound by
  definition.
- **A blocking call inside an async handler stalls the whole event loop.**
  Blocking work goes through `run_in_threadpool`.
- **Anything holding connections belongs to one event loop.** A pool is bound
  to the loop that created it, so it is created by the application lifespan and
  never by a module at import time.

**Enforced:** ruff `ASYNC` rules. This was found the hard way once — `send_email`
talks to SMTP synchronously and was safe only while handlers ran in a
threadpool — and is now a lint error rather than a thing to remember.

## Secrets

- Connector credentials are encrypted at rest with AES-GCM under
  `CONNECTOR_SECRET_KEY`, which is deliberately separate from `SECRET_KEY`:
  rotating the latter logs everyone out, rotating the former migrates data.
- **Which fields are secret is derived from the schema**, not from a list.
  Fields declared `SecretStr` are encrypted; there is no register to forget to
  update.
- Secrets never appear in API responses, error messages, logs or the
  repository. `.env` is untracked; `.env.example` carries placeholders.

**Enforced:** tests that a secret is absent from the public model, absent from
the stored column in plaintext, and absent from error text; a test that the
encryption key must decode to exactly 32 bytes.

## Frontend

- Server state lives in `@tanstack/vue-query`. Pinia holds only what the server
  does not — the token, UI state. The old frontend spread server data across
  stores with hand-rolled caches, and that is where its desynchronisation came
  from.
- **A screen asks for meaning, not for a look.** Anything with a choice of
  appearance is wrapped once in `src/shared/ui` and imported from there:
  `variant="danger"`, not `flat color="negative"`. `tokens.ts` is the only
  place that turns one into the other. What has no choice (`q-icon`,
  `q-separator`, `q-td`) stays as it is; the kit is not a facade over Quasar.
- `src/client` is generated from OpenAPI and never edited by hand. After
  changing routes or schemas, run `bash scripts/generate-client.sh`.
- Pure logic is separated from components so it can be tested without mounting:
  `jsonSchema.ts`, `treeNodes.ts`, `rows.ts` are plain functions.
- Elements are found in tests the way a user finds them — by role, text or
  `data-testid` — not by CSS classes and not by snapshots.

**Enforced:** ESLint forbids `src/stores/**` importing the generated client or
any feature, verified by introducing the import. ESLint also forbids, outside
`src/shared/ui`, every `q-*` the kit replaces — in both spellings Vue accepts,
because the rule matches the raw tag name and `<QBtn>` would otherwise walk
past — and forbids `useQuasar` in screens, which now use `useToast` and
`useConfirm`. Both were checked by attempting the bypass. A test compares the
`/ui-kit` showcase against the files in `shared/ui`, so a component cannot be
added without a demonstration. `vue-tsc` and ESLint cover the rest. The
pure-logic split rests on review.

## Tests

- Test layout mirrors the source: `app/adapters/postgres/fetch.py` →
  `tests/adapters/test_postgres_fetch.py`.
- **A test that would pass on an empty table tests nothing.** Paging and
  sorting run against `pg_catalog.pg_class`, which always holds hundreds of
  rows; the same assertions against a nearly empty application table passed
  while proving nothing, and that is why they were moved.
- Failure paths are tested, not only success: unknown column, unreachable host,
  missing capability, foreign owner.
- **A green unit test does not mean the user sees the result.** Captions in the
  catalog tree were computed, unit-tested and never rendered, because QTree has
  no `caption` prop. Anything user-visible is confirmed in the browser or by a
  Playwright scenario.

**Enforced:** `uv run pytest tests/ -q`, `bun run test:unit`,
`bunx playwright test`.

## Documentation of decisions

- A decision that shaped the code is written down with its reasoning, in
  `AGENTS.md` for the standing ones and in `docs/superpowers/specs/` for the
  full argument.
- **When a plan turns out to be wrong during execution, the plan is corrected
  too**, not just the code.
- Where the code knowingly differs from these documents, it is listed in
  "Known deviations" in [AGENTS.md](AGENTS.md) rather than left to be
  discovered.

**Review only.**

## A failing check is fixed in code, not weakened

Deleting a test, loosening an import contract, adding a suppression instead of
a type, dropping a capability check — these do not make a change ready, they
hide a defect: a check weakened this way is green forever and means nothing.
If a rule is genuinely wrong, it changes separately and with a reason, not on
the way to a green run.

## What holds it up

| Command | What it checks | State |
| --- | --- | --- |
| `uv run pytest tests/ -q` | backend behaviour | works |
| `uv run mypy app` | types, strict | works |
| `uv run ruff check app tests` | style, blocking calls in async, string-built SQL | works |
| `uv run lint-imports` | direction of dependencies between packages | works |
| `bun run type-check` | frontend types (build mode, needs Node, not bun) | works |
| `bun run lint` | frontend style, stores not reaching the API | works |
| `bun run test:unit` | pure frontend logic | works |
| `bunx playwright test` | end-to-end, needs db + backend + dev server | works |

A change is ready when every command touching the affected side is clean. That
is necessary, not sufficient: it says nothing about whether the thing asked for
was done.
