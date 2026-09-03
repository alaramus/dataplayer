# Migration roadmap

Last updated: 2026-09-03.

The order for moving useful behaviour from `dbwebtool` and `myquasar` into
DataPlayer. It is a route, not a promise to reproduce every old screen. The old
projects are evidence about workflows and edge cases; their files are never
copied into the rewrite.

This file answers one question: what to do next. What is already done is
recorded by [the spec index](superpowers/specs/README.md) and by git, and is not
inventoried again here.

## How to use this file

At the start of a migration session:

1. Read `AGENTS.md`, `ENGINEERING.md`, this file and the architecture file for
   the area being changed.
2. Continue the first unfinished item in the first unfinished phase. Do not ask
   which feature comes next unless an external decision genuinely blocks it.
3. Inspect the named old sources before designing the slice. Port the useful
   behaviour, not its API, state management or component structure.
4. If the slice introduces a lasting contract, write the decision, architecture
   statement and spec before implementation.
5. Implement tests with the change. Run validation only after the user approves
   the exact commands, as required by `AGENTS.md`.
6. When a slice is complete, remove its item, add its spec to the index and
   update the date above. A closed phase collapses to one line below.

Legend:

- `[~]` implementation is written but validation is still pending;
- `[ ]` queued;
- `[?]` discovery is required before the implementation boundary is known.

## Closed

| Phase | Closed | What settled it |
| --- | --- | --- |
| 0 — stabilise the bounded chart slice | 2026-08-30 | [D35](superpowers/specs/2026-08-30-bounded-page-charts-design.md) |
| 1.1 — relationship navigation | 2026-08-30 | [D36](superpowers/specs/2026-08-30-reference-navigation-design.md) |
| 1.2 — safe PostgreSQL structure editing | 2026-08-30 | D27, D29, D30, D37, D38, D39, D40 |
| 1.3 — bulk data movement through the grid | 2026-08-30 | D41, D42, D43, D44, D45, D46 |
| 1.4 — file-source depth | 2026-08-31 | D47, D48, D49, D51, D52, D53 |
| 1.5 — PostgreSQL-specific operations | 2026-09-01 | D54, D55, D56, D57 |
| 2 — share a view | 2026-09-01 | D58, D59, D60, D61 |
| 3 — query editor | 2026-09-02 | D62, D63, D64, D65, D66 |
| 3.5 — the rest of the old application's daily operations | 2026-09-02 | D67 through D79 |
| 4 — server-owned jobs: Docker services, backup and restore | 2026-09-03 | D80 through D87 |

Each of those has a spec in [the index](superpowers/specs/README.md), dated the
day it closed, and a home in `docs/architecture/`. With 1.5 validated, phase 1
is closed: PostgreSQL covers the common daily table workflow, files open in a
representation appropriate to their content, and what remains of the old
behaviour is classified as a deliberate later capability rather than an unknown
gap. Phase 2 closed the same day: a view has an address, following it is
governed by the grant model D33 already had, and asking for access is a durable
request rather than a message that is lost when nobody is listening. Phase 3
closed on 2026-09-02: PostgreSQL SQL is written in a durable document, run and
cancelled as a bounded asynchronous run, read back as a stable snapshot, and
— once a person has deliberately left read-only — allowed to change data and,
within a closed vocabulary, structure.
Phase 3.5 closed the same day. It was a list rather than a contract — the
operations of the old application that were still missing, each small enough
to land on its own — and it ends with the one that was written down and
deliberately left out when the PostgreSQL inventory was made: making a
database user.
Phase 4 closed on 2026-09-03. What it actually built is the owned
asynchronous job — a row with named steps that outlives the request, the
socket and the process — and two users of it. A person asks for one of the
services this server is allowed to run, watches it become ready and receives
an ordinary encrypted connector; and a database is copied out into a file of
their own storage, or written back from one, by the real programs running in
a container of the server's own version. Whether any of it is offered at all
is a question about the machine, asked of it, and answered off by default.

## Priority order at a glance

| Order | Phase | Relative size | Why it is here |
| --- | --- | --- | --- |
| 5 | Optional Redis infrastructure | Medium | Needed only when multiple backend processes must share cache or coordination state |
| 6 | Add adapter families deliberately | Ongoing | Breadth is useful only after one complete adapter can exercise each contract family |
| 7 | Charts and dashboards, second slice | Large | Whole-source aggregation, saved layouts and a history to draw over require contracts absent from the bounded chart |
| 8 | User-configured AI agent | Very large | Must reuse safe tools, permissions, confirmations and disclosure rules built earlier |

## Phase 5 — optional Redis infrastructure

The rewrite already has D31's bounded, process-local `DataCache`. Redis is not
needed to make a single-process installation correct. Add it when deployments
need shared cache entries and invalidation across backend workers, not merely
because the old project had a Redis object.

Sequence:

- [ ] Extract a cache backend protocol without weakening D31's exact keys,
  in-flight coalescing, LRU/TTL bounds or post-mutation invalidation rules.
- [ ] Define versioned serialization, namespace by deployment and user, and
  decide whether sensitive fetched values require encryption in Redis.
- [ ] Implement optional Redis cache storage plus a cross-worker invalidation
  channel. Failure must degrade to direct reads, not take data access down.
- [ ] Add configuration, health reporting, TLS/auth examples and an optional
  Compose service; keep the in-memory backend as the default.
- [ ] Only after measurement, reuse Redis for distributed locks, job fan-out or
  share acceleration. Snapshot truth and job truth remain durable elsewhere.

Exit condition: two backend workers observe the same invalidation behaviour,
and turning Redis off changes performance rather than correctness.

## Phase 6 — add adapter families deliberately

Do not port seventy adapters as seventy partial packages. Add one representative
of a new contract family, settle the capability, then add siblings cheaply.

Recommended order after Phase 5:

1. DuckDB or SQLite as a source of its own — somebody's `.duckdb` or `.sqlite`
   file, with a catalog, a grid and structure. The engine itself arrived with
   D77 as the file source's, and a database file is a different thing: it has
   tables that persist, and this one runs read-only over files and is thrown
   away.
2. MySQL for a second networked SQL pool and dialect.
3. Redis/Valkey as a user data source, distinct from infrastructure Redis.
4. S3/MinIO for an object-store catalog and streaming file transfer.
5. Kafka or RabbitMQ only after a stream/topic contract is designed; a stream is
   not a paged table pretending to have rows.

Every adapter must meet the same acceptance checklist:

- [ ] self-described options and variants, secret splitting and connection
  string behaviour;
- [ ] connection check, resource ownership and cleanup;
- [ ] honest catalog/fetch/action capabilities and safe errors;
- [ ] permissions and cache policy;
- [ ] backend contract tests, frontend capability behaviour, an end-to-end
  scenario and architecture documentation.

## Phase 7 — charts and dashboards, second slice

The bounded page chart in D35 stays honest and small. The next chart round must
not silently reinterpret it as a whole-relation result.

Old sources to inspect:

- `myquasar/src/myapp/views/ViewChartNew/`;
- `myquasar/src/myapp/views/Dashboards/`.

Sequence:

- [ ] Define an adapter-owned aggregate request with a closed group/measure/
  function vocabulary and hard cardinality limits.
- [ ] Add whole-result aggregate charts as a distinct data source from the
  bounded page chart.
- [ ] Define saved chart ownership and persistence before adding names or URLs.
- [ ] Define a dashboard layout and widget versioning before multiple charts
  share a screen.
- [ ] Add realtime metric widgets only for sources with a real subscription
  capability. Polling and streaming remain different contracts.
- [ ] **A history of metrics, and charts over it.** The old application's
  `include_story` recorded readings so they could be drawn later. It is here
  because it is a chart over time before it is anything else, and it is the
  one item in this phase needing a decision before design: what is recorded,
  where it is kept, who prunes it, and whether it is a source of its own or a
  table of the application's. If the answer is "a source of its own", it is a
  phase 6 adapter with a chart on top rather than a chart with storage behind
  it.
- [ ] AI suggestions may return only the closed chart specification and belong
  after the disclosure and tool rules in Phase 8.

## Phase 8 — user-configured AI agent

The old ChatAI area contains useful interaction ideas but is several products at
once: provider settings, local models, chat history, tools, MCP, memory,
attachments and external agents. Port it as independent slices.

Old sources to inspect:

- `myquasar/src/myapp/components/ChatAI/`;
- `myquasar/src/myapp/components/AiPanel/`;
- `dbwebtool/webdb/ai_handler/`;
- `dbwebtool/webdb/dashboard/agents.py`.

Sequence:

- [ ] Provider/model configuration with encrypted per-user keys and explicit
  third-party data disclosure.
- [ ] One streaming conversation surface, cancellation and a retention/export/
  deletion policy.
- [ ] A typed tool registry that wraps existing catalog, fetch, query, action,
  chart and share capabilities. Read-only tools are the default.
- [ ] Confirmation for every mutation, clear tool-call progress and an audit
  record. The model never receives connector credentials.
- [ ] User instructions and a saved agent definition with a bounded tool
  allowlist.
- [ ] Attachments, memory, MCP/external agents and local browser/server models
  only as later, separately consented capabilities.

Exit condition: a user can configure one agent, understand where their data is
sent and let it use the same permission-checked operations available in the UI.

## Explicitly deferred

These old areas are not on the main migration path until a user goal promotes
one of them: web terminal, MRP, trading screens, translation, karaoke/media
generation, generic monitoring agents, Kubernetes/cloud control panels and
one-off adapter demos. Their presence in the old repository is not evidence
that they belong in the platform core.

Searching the text inside files was dropped from phase 3.5 rather than
deferred: names across the tree landed as [D76](architecture/sources/contract.md),
and the other half is a different request — its answer is lines rather than
nodes, so it needs its own result shape, its own ceilings and a way to stand at
a line. It returns when somebody wants it.

An immutable snapshot of fetched rows — what phase 2 used to be — is deferred
with its reason rather than dropped. It answers "the recipient must not be
given the connection", and every recipient today is a colleague who can hold a
grant; a frozen copy would only go stale in their hands. The argument and the
shape to return to are in
[the sharing spec](superpowers/specs/2026-09-01-shared-view-links-design.md).

Deferred inside PostgreSQL, with the reason in the spec that deferred it:
backup and restore (needs Phase 4's owned jobs), monitoring statistics
(Phase 7), Grafana (Phase 6), database roles, ORM code generation, diagram and
similarity features, and every TimescaleDB operation. An action over ticked
rows — cancelling a query is the first one to want it — is a contract gap the
project does not have and will not invent for a single command.

## Patterns that must not be ported

- dynamic `getattr` action dispatch from a client method name;
- client-built SQL identifiers or predicates;
- server data duplicated into Pinia stores;
- generic screens branching on adapter names;
- Redis as an untyped global dictionary;
- arbitrary Docker Compose or shell text accepted from the browser;
- administrator access bypassing data grants;
- chart or AI payloads accepting executable renderer/tool configuration;
- a large fetch limit used as export, sharing or aggregation.
