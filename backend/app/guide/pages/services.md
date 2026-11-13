# Services and terminals

DataPlayer can start database servers and other sources for you on the machine
it runs on, and open terminals on your connections. Both live in the panel at
the foot of the screen, opened by their tools on the bottom left rail.

## Starting a server here

Where this installation may run containers, the panel of a kind of source in
**New connection** offers **Start … here** — PostgreSQL, MySQL, Redis, an SSH
server and others. How it asks and what you get is on the
[Connections](connections.md) page. The server runs in Docker on this machine,
and its connection is made for you.

A button that is greyed out says why when you point at it: this installation
may not run containers at all, or not that kind.

## The Services tool

**Services** lists the servers started here for you, with the state of each
and of its container.

- **Stop it** stops a server; what is stored in it stays. **Start it** starts
  it again.
- **Start over** removes a server that failed to start, and its data, and tries
  again.
- **Where it listens** shows the host, port, user and database to reach it
  from your own tools, and a connection string. Its password is shown only
  once, when the server is made, unless you typed your own.
- **What it printed** shows the server's own output.
- **Remove this service** removes the server and everything stored in it.
  **Remove the connection as well** removes its connection too.

Starting, stopping and removing run in the background; the activity bell shows
how they are going.

## Terminals

**Terminals** opens a terminal on one of your connections:

- on an SSH connection, a shell on that server;
- on a database connection that offers it, its own client program — `psql`,
  `mysql`, `cqlsh`, `zkCli`, Kafka's tools, `rabbitmqadmin` and others —
  signed in as the connection. It runs in a container this server starts, so it
  is offered only where containers may run. The page of each kind of source
  says what it opens.

Several terminals can be open at once, each in a tab of the panel. A terminal
keeps every key to itself, Ctrl+K included. Closing its tab ends it.

Terminals are opened only on connections you own.

## Backups

A database that can be copied out has **Backups** in its catalog's actions
menu: **Copy this database out** makes a backup, a file in your own storage;
**Restore** writes one back, replacing what it holds; deleting removes the
file. The page of each kind of source says whether it has backups.

## Logs

**Logs**, on the bottom left rail of an administrator, reads the server's own
log: filtered by level and by process, searched by text or by the reference a
failure message gives, and followed as it grows.
