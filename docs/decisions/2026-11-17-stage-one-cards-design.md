# Stage one of the sources roadmap: cards only

Decision D377. The sources roadmap begins with products that are the original
under another name. Each of them can be a card (D264) of a type that already
exists, so it needs no adapter and no form of its own.

## What it does

- **Self-hosted products.** Valkey and KeyDB are cards of `redis`, Redpanda
  of `kafka`, Percona Server of `mysql`, and Citus and ParadeDB of `postgres`.
  TimescaleDB becomes a card of `postgres` too: it already had a template, and
  once `postgres` has cards every template must belong to one. Each card offers
  to start the product's own image:

  | Card | Image |
  | --- | --- |
  | Valkey | `valkey/valkey:9.0` |
  | KeyDB | `eqalpha/keydb:x86_64_v6.3.4` |
  | Redpanda | `redpandadata/redpanda:v26.2.7` |
  | Percona Server | `percona/percona-server:8.4` |
  | Citus | `citusdata/citus:14.2` |
  | ParadeDB | `paradedb/paradedb:0.26.7-pg18` |

- **Hosted products.** Supabase, Neon, Amazon RDS for PostgreSQL, Azure
  Database for PostgreSQL and Cloud SQL for PostgreSQL are cards of `postgres`.
  Amazon RDS for MySQL, Azure Database for MySQL and Cloud SQL for MySQL are
  cards of `mysql`. Aurora is part of the RDS card rather than a card of its
  own. These cards start nothing. Through `CatalogFace.options` and `note`
  (D373) they fill in what the provider always names the same, such as
  Supabase's `postgres` user, and link to the provider's page on finding the
  host and the password. A cloud on two types appears as two cards, named the
  way the provider names its products, and both carry the cloud's logo.

- **The version names the product.** MySQL already showed "MariaDB 11.4".
  Percona Server now shows as "Percona Server 8.4.11", read from
  `@@version_comment`. A Redis server shows as "Valkey 9.0.7", read from
  `server_name` and `valkey_version`, or as "KeyDB 6.3.4", read from its
  `executable`. Valkey reports `redis_version` 7.2.4 to stay compatible with
  clients, so that field alone would give the wrong number. Citus and ParadeDB
  are already listed among a database's extensions. Kafka shows no version, and
  neither does Redpanda.

- **A template's command may name its own container.** Kafka's template reads
  its own address in a shell and advertises it (D311). Redpanda's entrypoint
  hands its arguments straight to `rpk` with no shell. The image's own
  default listeners were tried as well, but its entrypoint writes listener
  names that `rpk` then refuses. `OwnName(prefix, suffix)` is therefore a
  command value resolved to the container's name, which the server decides
  and the application already reaches the service by.

- **Connections a service made before** get the card of the template that
  made them, through migration `b8e3f2a6c9d4` for `postgres`, `timescaledb`,
  `redis` and `kafka`. This is what c3d8e1f5a2b7 did for MariaDB and ScyllaDB.

## Tests

- Each image has a service in `compose.override.yml` behind `tools`, and a
  smoke test in `tests/adapters/test_product_cards.py`. The test checks the
  connection, reads the version or the extension, and opens the catalog's top
  level. For Redpanda it also lists a topic it has made.
- These servers are marked `local` in `tests/utils/services.py`. Without one,
  its tests are skipped even under `--require-services`. Six more images in
  every CI run would cost more than the smoke test is worth.
- Unit tests cover the cards and their options against each type's form, the
  templates, `OwnName` in a plan, and the readers of the version.

## Rejected

- **A dozen hosted cards.** The roadmap warns that many logos of one server
  make the catalog harder to read. Only the three large clouds, Supabase and
  Neon are cards.
- **Detecting Redpanda.** The Kafka protocol does not say which broker
  answers. Redpanda's admin API would, but it is another port and another
  client for one line of text.
- **KeyDB by `INFO keydb`.** That section exists, but asking for it costs every
  Redis connection a second round trip. KeyDB's program name answers in the
  same `INFO server` reply.
- **Drawn logos for every product.** Valkey, Redpanda, ParadeDB and Percona
  are taken from their own repositories. Supabase, Google Cloud, Azure and AWS
  come from devicon, and Neon from simple-icons. Only Citus and KeyDB, which
  publish no SVG, get a letter on their colour.
