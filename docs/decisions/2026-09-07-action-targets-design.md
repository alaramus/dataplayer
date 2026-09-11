# Action targets and availability

## Problem

The catalog replaced selected groupings with checked rows before asking about
actions. A checked table consequently disabled Rename schema. Creation treated
every displayed schema as a target for the same form, disabling CSV import and
the table designer when several schemas were displayed, although both forms
already choose one destination.

## D118. Selection scope and destination choice are separate

Keep the registry and execution guards. Extend the action's subject rather than
teaching the menu PostgreSQL names. `group` receives explicitly selected
groupings independently of row ticks. `destination` opens a workflow that
chooses one destination; availability means at least one candidate admits it,
not that the form can run on the entire candidate set. Existing `level`,
`children` and `node` subjects keep their meanings. Node selection still prefers
checked rows over selected groupings, useful for model export.

The listing returns `available_node_ids` and `unavailable_reason` from the same
source offers used to decide applicability. For ordinary subjects all targets
must qualify and multiple targets require `bulk`. A destination workflow gets
one eligible initial target, preferring a displayed place, and never receives
the candidates as an execution batch. Its existing destination control remains
editable. Execution and preview recheck source availability and permissions.

Destination candidates are the level's groupings, including when no grouping is
displayed. System groupings are rejected by the source. Missing or failed
availability answers disable the affected command. Group actions never fall
back to the current directory. Targets, labels and rename defaults come from
the same subject and are captured when the form opens.

## Registry audit

| Source | Actions | Subject | Cardinality / additional conditions |
| --- | --- | --- | --- |
| PostgreSQL | New schema | level | One database root; independent of selection |
| PostgreSQL | Rename schema, Drop schema | group | One non-system schema; drop previews that schema |
| PostgreSQL | Load from CSV, New table | destination | One chosen schema per run; forms already offer destination selection |
| PostgreSQL | Rename relation | node | One non-system table or view |
| PostgreSQL | Move to schema | node | One or many non-system relations; one destination, a result per relation |
| PostgreSQL | Drop relation | node | One or many; whole-set preview and atomic execution |
| PostgreSQL | Model as code | node | Selected relations, or selected schemas without checked rows; bounded set download |
| PostgreSQL | New role | node, rows surface | Roles report only; owner only |
| Files | New folder, Upload, Paste | children | Current directory; row selection is irrelevant; paste requires a clipboard |
| Files | Rename, Connect folder | node | One selected node; connection requires a child directory and ownership |
| Files | Delete, Download | node | All selected eligible nodes; root cannot be changed |
| Files | Create archive | node | Selection allowed; runtime requires all targets to share a parent directory |
| Files | Extract archive | node | All selected files must be supported archives |
| Redis | Write string, hash, list, set, sorted set, stream | level | Current database or namespace; root and keys are not destinations |
| Redis | Delete, Set expiry, Remove expiry | node | One or many selected keys |
| Client | Details | checked rows | Exactly one describable node |
| Client | Relationships | checked rows or displayed nodes | Existing diagram capability and bounded selection |
| Client | Copy, Cut | checked rows | Nonempty selection on a source with paste |
| Client | Backups | connection | Source and runtime support; unrelated to selection |

Mixed selections are never silently reduced for destructive or node actions.
File archive set restrictions and runtime conflicts remain execution checks;
this change does not promise a set-level preview where none exists.

## Validation

Add registry/availability matrix tests, route coverage for eligible destinations
and cardinality reasons, menu target/label regression tests, and browser coverage
for checked rows alongside schema actions and CSV creation with multiple schemas.
Run checks only with the user's explicit approval, as required by AGENTS.md.

Prepared commands (not yet run):

From the repository root, start the test dependencies:

```bash
docker compose up -d db redis
```

From `backend/`:

```bash
uv run pytest tests/adapters/test_actions.py tests/adapters/test_postgres_actions.py tests/adapters/test_file_actions.py tests/adapters/test_redis_actions.py tests/connectors/test_action_routes.py tests/connectors/test_table_design_routes.py -q
uv run mypy app
uv run ruff check app tests
uv run lint-imports
```

From `frontend/`:

```bash
bun run test:unit src/features/catalog/actions.spec.ts src/features/catalog/CatalogActions.spec.ts src/features/catalog/ActionDialog.spec.ts
bun run type-check
bun run lint
bun run build
```

From the root, check documentation and rebuild the backend with the new API.
Prestart also restores development users and fixtures after backend tests:

```bash
bash scripts/check-docs.sh
docker compose up -d --build backend
```

Warm `bun run dev` from `frontend/`, then run the focused browser scenarios from
that directory with `PLAYWRIGHT_BASE_URL=http://localhost:5173`:

```bash
bunx playwright test tests/actions.spec.ts --reporter=line
```
