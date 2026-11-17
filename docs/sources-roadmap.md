# Sources roadmap

Where the list of sources is going, and in what order. Everything here is
wanted; the order runs from the cheapest to the most expensive, so the catalog
grows steadily while the large pieces are being built.

This is a plan, not a record. What is done is recorded by git and the spec
index ([decisions/README.md](decisions/README.md)); a source moves out of this
file into its own architecture file when it is built.

## Where we are

Built: PostgreSQL with TimescaleDB, MySQL and MariaDB, SQLite, ClickHouse,
MongoDB, Redis, Cassandra and ScyllaDB, Kafka, RabbitMQ, ZooKeeper, Binance,
file storage (local and over SFTP) and SSH. Stage 1, the cards of products
that are one of these under another name, is done as D377
([contract](architecture/sources/contract.md)).

## How cost is judged

- **A card** costs least. One source type may show a card per product
  ([D264](architecture/sources/contract.md)): same form, same driver, its own
  name, logo and service template. MariaDB is the precedent.
- What makes a card cheap is not the wire protocol but how much of the
  original's **catalog and DDL** the product really has. A product that speaks
  the protocol but lacks `pg_catalog` or `information_schema` is a quirk list,
  and a product with its own DDL is close to a new adapter.
- **A test server** is part of every item. Whatever has no Docker image needs
  an emulator, and where none exists the cost goes up: only unit tests run
  locally, and the end-to-end check needs a real cloud account.
- A new source type follows the shape of the existing ones: six slices
  (catalog, values and pages, row edits, structure, reports and search, actions
  and console), its service and lab, its page in the user's guide.

## Stage 2 — cards with a quirk list

Same driver, but the server answers differently somewhere: the adapter detects
the product from the server, and a capability the product lacks answers that it
is missing rather than failing.

| Product | Base type | Test server | What differs |
| --- | --- | --- | --- |
| Dragonfly | `redis` | `dragonflydb/dragonfly` | `INFO`, `MEMORY USAGE`, `OBJECT`, `CONFIG`, Lua and cluster emulation |
| YugabyteDB | `postgres` | `yugabytedb/yugabyte` | PostgreSQL fork; some DDL and statistics views |
| TiDB | `mysql` | `pingcap/tidb` | `AUTO_RANDOM`, foreign keys, some `information_schema` |
| CockroachDB | `postgres` | `cockroachdb/cockroach` | partial `pg_catalog`, limited `ALTER COLUMN TYPE`, no extensions |
| SingleStore | `mysql` | `singlestore/cluster-in-a-box` | shard and sort keys in DDL |
| Greenplum | `postgres` | community images only | old PostgreSQL base, `DISTRIBUTED BY` |

## Stage 3 — cloud sign-in

Not a product but a way of signing in, orthogonal to the type: one variant of
the connection options, shared by `postgres` and `mysql`.

- **AWS IAM database authentication.** The password is a token signed locally
  with SigV4, valid for 15 minutes and checked only when a connection opens,
  so an open connection outlives it. TLS is required, ideally `verify-full`
  against Amazon's CA bundle.
- **AWS Secrets Manager.** An ordinary password that AWS rotates; it is read
  from the secret before connecting.
- **Azure Entra ID** and **Google Cloud IAM.** Tokens of about an hour, same
  idea.

What it changes: the pool asks for credentials on every new connection instead
of receiving a finished connection string once. Traps: through an SSH tunnel
the token is signed for the real RDS host, not for the tunnel's `localhost`;
the signing needs `botocore` at most, not the whole of `boto3`. Only the token
signing can be tested locally, against AWS's published vectors.

## Stage 4 — medium new types

Each is a new package with its own catalog, but small or able to lean on
something already built.

| Source | Leans on | Test server | Notes |
| --- | --- | --- | --- |
| DuckDB | SQLite's shape and the file-SQL sandbox | none needed | a file in personal storage; external access off and configuration locked, as in [file-sql](architecture/sources/file-sql.md); one writer per file; a file from a newer DuckDB is refused clearly; `STRUCT`, `LIST`, `MAP` shown as documents. MotherDuck later as a second card |
| S3, Google Cloud Storage, Azure Blob | the explorer's storage interface | MinIO, fake-gcs-server, Azurite | a new storage behind the existing explorer; Parquet and CSV in a bucket through DuckDB |
| etcd, Consul KV | ZooKeeper's tree of keys | `bitnami/etcd`, `hashicorp/consul` | leases and TTL instead of ephemeral znodes |
| Schema Registry, Kafka Connect | the Kafka type | Confluent or Karapace images | schemas and connector status next to the topics |
| NATS JetStream | Kafka's and RabbitMQ's message rows | `nats` | streams and consumers |
| dbt artifacts | the graph view | none: files | `manifest.json` and `run_results.json` read as a model graph with test results and timings; dbt Cloud API later |
| Trino | the SQL console | `trinodb/trino` | read-mostly; its catalogs become top-level nodes |
| Materialize, RisingWave, QuestDB | `postgres` | official images | read-only cards: no row or structure edits |
| StarRocks, Doris | `mysql` | official images | read-only and console first; their DDL is closer to ClickHouse than to MySQL |
| Prometheus, Loki | dashboards | official images | PromQL and LogQL as the console; series as rows |
| InfluxDB | dashboards | `influxdb` | buckets and measurements |

## Stage 5 — large new types

Full adapters with their own model of data, or of work rather than data.

| Source | Test server | Why it is large |
| --- | --- | --- |
| Microsoft SQL Server | `mcr.microsoft.com/mssql/server` | a new dialect, schemas, its own DDL, backups |
| Oracle | `gvenzl/oracle-free` | a new dialect, schemas as users, its own types |
| Elasticsearch, OpenSearch | official images | indices and mappings instead of tables; search DSL as the console |
| Airflow | the official compose | DAGs, runs and task instances as rows; logs and XCom as content; trigger, pause, clear and mark as actions; a pipeline card that starts a DAG |
| Dagster, Prefect | official images | the same shape as Airflow once it exists; Dagster's assets map onto tables |
| Iceberg, Delta Lake | Iceberg REST image with MinIO | tables in a lake: schema, snapshots, time travel; needs stage 4's object storage |
| AWS Glue, Hive Metastore, Unity Catalog | Hive image; Glue and Unity need the cloud | catalogs over the lake tables |
| DynamoDB | DynamoDB Local | keys and indexes instead of a schema |
| Neo4j | `neo4j` | a graph instead of rows; fits the 2D and 3D diagrams |
| Pulsar, Kinesis | Pulsar standalone, LocalStack | the remaining message systems |
| Generic REST and GraphQL | none: a mock server | an endpoint, its paging and the path to the array become a table, as declared tables over Redis keys do; covers most SaaS. Google Sheets and Airtable as cards on it |
| Snowflake | fakesnow only | no server to run; a dry run with the cost of a query before it runs |
| BigQuery | bigquery-emulator | the same; bytes scanned shown before running |
| Databricks SQL, Redshift | none | cloud only; Redshift is PostgreSQL 8.0 underneath, so not a card |

## Order inside a stage

Within a stage, take first what has a test image and what is asked for most.
A stage need not be finished before the next one starts: stage 4's object
storage, for example, is the way into stage 5's lake tables.
