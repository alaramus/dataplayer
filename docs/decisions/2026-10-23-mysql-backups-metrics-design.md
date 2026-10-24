# MySQL backups and metrics

Decisions D240 and D241. The rest of the sixth slice of the MySQL source:
backing a database up and putting it back, and reporting to dashboards.

## Backups: the dump program of the server's own family

Backups run a program in a container of its own (D87); the source only says
which. PostgreSQL says `pg_dump` of its major version. A MySQL connection may be
MySQL or MariaDB, and each ships its own programs: `mysqldump` and `mysql`,
`mariadb-dump` and `mariadb`. The image is the server's own family and release,
`mysql:8.4` or `mariadb:11.4`, read from the server when the programs are named.
A dump by the other family carries collations and statements this server may
not know, and a dump by an older release may miss what the server has.

Before choosing, both programs were run in containers on the compose network,
against both test servers, with the arguments the adapter builds. A table with
binary values, a view and a procedure were dumped, dropped and restored.

### One database

PostgreSQL's connection always names one database, and its backup is of that
database. A MySQL connection may name none and see many. A dump of every
database a user can see would make a restore write into databases the
restoring connection never named, so the backup is of the database the
connection names. A connection that names none is told so instead of being
offered a backup.

The dump program takes the database as an argument of its own. A name beginning
with a dash would be read as an option, so such a database is not offered a
backup. The client is given it as `--database=`.

### The dump and the restore

- `--single-transaction` for a consistent dump of InnoDB tables without
  locking them;
- `--routines --triggers --events`, so the backup is the whole database;
- `--hex-blob`, so binary values survive in a text file;
- `--no-tablespaces`, which otherwise needs the PROCESS privilege;
- on MySQL, `--set-gtid-purged=OFF`. A server with replication of its own
  refuses a dump that sets its GTIDs.

A restore is the client running `source` on the file, into the connection's
database. The dump drops each table, view and routine before making it again,
which is what makes it a restore rather than a merge. The client stops at the
first statement the server refuses.

The password travels in `MYSQL_PWD`, which both clients read. The arguments
are visible to anything on the machine that can list processes. TLS is as the
connection has it (D228): used when offered, the certificate not checked.
MariaDB's client checks it by default, so it is told not to.

### What is checked before a restore

PostgreSQL's restore lists the archive's table of contents first. A MySQL
backup is SQL, so the first lines are read instead. A dump says which family
made it in its heading: `-- MySQL dump` or `-- MariaDB dump`, after the
sandbox line newer MariaDB programs write first. A file without that heading is
not restored, and neither is a dump of the other family.

## Metrics: the server's counters

Dashboards poll a connection that reports (D128). PostgreSQL reports its
database's counters from `pg_stat_database`. MySQL keeps nothing per database:
its status variables are the server's. So the layout is *MySQL server*, and
only the size is of the database the connection names, or of every database
not the server's own when it names none.

Everything is read in one `SHOW GLOBAL STATUS` with the names bound. Any user
may run it on both servers. `performance_schema.global_status` would need a
grant on MySQL, and MariaDB keeps the same answer in `information_schema`.

The series:

- connections connected and running, as gauges;
- statements per second, by kind;
- rows per second read, inserted, updated and deleted;
- buffer pool read requests and reads from disk;
- bytes received and sent;
- slow queries, aborted connects and aborted clients.

MariaDB keeps no `Innodb_rows_*`, so a series names the variables it may be
read from, in order. On MariaDB, rows read come from `Rows_read`, and rows
written from the handlers' counters, which count every engine's.
