# Stage two of the sources roadmap: Dragonfly and TiDB

Decision D378. Stage 2 of the sources roadmap listed six products that speak
an existing type's protocol but answer it differently: Dragonfly, YugabyteDB,
TiDB, CockroachDB, SingleStore and Greenplum. The point of the stage is to
widen the list of connections, not to finish a list, so it was cut to the
two that cost least for what they are asked for.

## What was dropped, and why

- **CockroachDB.** Run against the PostgreSQL adapter, it connects and lists
  schemas. It then fails on four things the basic path rests on:
  `reltuples` is null, `pg_indexam_has_property()` is missing (every
  description of a table and every structure change reads it), and `xmin`
  and `ctid` are missing (every page of rows and every row edit uses them).
  The last of these means rewriting how the PostgreSQL adapter versions a
  row, in code every PostgreSQL connection shares.
- **YugabyteDB.** A real PostgreSQL fork, but its image asks for more memory
  than a service is given (D86), and it is asked for less.
- **SingleStore.** Its image needs a licence key and about 4 GB.
- **Greenplum.** Closed since 2024, with no official image, and built on
  PostgreSQL 12, below the floor backups are made for.

## How the differences were found

Each product's server ran the type's whole test suite: Redis's against
Dragonfly, MySQL's against TiDB, its fixture stripped of the spatial column
TiDB cannot make. Every failure was then fixed in the adapter, refused with
a sentence, or found to be the product's own behaviour.

- **Dragonfly** failed every test with a password and none without one. The
  Redis driver (8.x) speaks RESP3 and sends `HELLO 3` before `AUTH`, which
  Redis answers and Dragonfly refuses. Naming the `default` user makes the
  driver sign in inside `HELLO`. RESP3 already needs Redis 6, which has that
  user, so no server that worked before stops working.
- **TiDB** was refused at once: it calls itself MySQL 8.0.11, under the
  8.0.16 floor. It is now a flavour of its own, read from `-TiDB-v8.5.7`
  and held to 7.5, the oldest release still supported. After that:
  - `TABLE_CONSTRAINTS` has no `ENFORCED`. The checks are read without it,
    and enforced as far as `tidb_enable_check_constraint` says. That switch
    is off by default, and when it is off TiDB does not keep checks at all.
  - `START TRANSACTION READ ONLY` is refused unless TiDB's no-op functions
    are switched on, and switched on it would protect nothing. `START
    TRANSACTION READ ONLY AS OF TIMESTAMP NOW()` refuses every write,
    `FOR UPDATE` included. But it did not see a table made a moment before
    on the same server, and a person reading straight after writing would
    see the past. A read is therefore an ordinary transaction, always
    rolled back. The class of a statement already keeps writes and DDL out
    of a read (D233), and that is now the only guard.
  - Processes, variables and status are in `information_schema`, as on
    MariaDB.
  - `EXPLAIN FORMAT=JSON` does not exist, and the plan is refused with a
    pointer to the console.
  - The sample data has spatial columns and triggers, so the TiDB template
    sets `sample_data=False`: the form does not offer it, and an automatic
    start does not ask for it.
  - Backups are refused: TiDB's dump program is Dumpling, and the backups
    here run the server family's own client image.
  - Text compares by bytes (`utf8mb4_bin`), so filters are case-sensitive.
    That is how TiDB behaves, not a fault here.

## The TiDB template

TiDB has no environment variable for root's password; `--initialize-sql-file`
reads SQL on the first start. The image's entrypoint is the server itself,
so a template now has an optional `entrypoint`, empty by default. TiDB's is
`sh -c`. The script is a constant, and the password reaches it as `$1`,
with `'` and `\` doubled for SQL. It was checked by starting the image with
a password containing both and signing in with it. TiDB runs on its built-in
store (`unistore`), one node, data under `/var/lib/tidb`.

## Tests

- Dragonfly and TiDB are in `compose.override.yml` behind `tools`, marked
  `local` like the stage-one servers: skipped without them, even under
  `--require-services`.
- The smoke tests sign into Dragonfly with a password and find a key, then
  read, edit and refuse on TiDB.
- Unit tests cover the TiDB profile and its read statement, Dragonfly's
  version, the templates, the entrypoint in a plan and in the body sent to
  Docker, and the card lists.
