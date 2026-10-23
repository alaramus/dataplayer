# MySQL services

Decision D244. Starting a MySQL or a MariaDB server on this machine, as
PostgreSQL, TimescaleDB and Redis already can be (D80).

## Two templates for one source type

The source type is one for both servers (D228), but what runs is an image, and
the two servers are two images: `mysql:8.4` and `mariadb:11.4`. They are the
releases the suite runs against, and both are long-term support. Both become
an ordinary MySQL connection; which server it is, is read when it connects. So
the connection window offers both on the MySQL type: **Start MySQL here** and
**Start MariaDB here**.

## Signed into as root

The images can make an ordinary account with all privileges on one database.
Rather that, or root?

- **An ordinary account.** Narrower, but it cannot make accounts, see other
  connections' processes, or dump routines and events without grants it
  lacks. New user (D243), the Processes report and backups (D240) would each
  be refused on a server that belongs to the person who started it.
- **Root.** What PostgreSQL's template does: its image's `POSTGRES_USER` is a
  superuser.

Root is chosen. The images take root's password from `MYSQL_ROOT_PASSWORD` and
`MARIADB_ROOT_PASSWORD`, made up here unless chosen (D88). They refuse an
ordinary user named root, so the user is not a name to choose. The database
the connection opens on is the one the images make, `dataplayer` unless
another is named. Neither image may run without a password: a server that
trusts every connection is not one this application starts.

## Waiting for it

A first start initialises a data directory and restarts the server once
before it listens on its port, which takes longer than PostgreSQL does. The
service waits up to three minutes, asking the connection's own check
(D83).
