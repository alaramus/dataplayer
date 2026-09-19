# An SSH server this application starts

Date: 2026-09-19. Decisions: D153.

Status: implemented with this specification.

## What was asked

PostgreSQL, TimescaleDB and Redis can be started as services from the catalog
(D80–D90). The owner asked for the same for SSH, which the old application
offered: a Linux machine to try the explorer and the terminal on, without a
server of one's own.

## What was decided

**D153 — a template, and a server key pinned from the first answer.**

- The template runs `lscr.io/linuxserver/openssh-server`, pinned by tag like
  every other. It is the image the old application started and the image the
  development override runs as `sshd`. Its home is `/config`, and the one named
  volume goes there, so the user's files and the server's keys outlive a
  restart together.
- The account is `dataplayer` with a password made up here, exactly as for
  PostgreSQL; a chosen start may name the user and the password. Password
  sign-in is on and `sudo` asks the same password. There is no shape without a
  password.
- The connector cannot be filled with the server's key: nothing knows it before
  the container has made one. The readiness probe, which already waits until
  the source answers, asks for the key first and pins it. It answers with the
  options it succeeded with, rather than a yes, and the job saves those. Which
  field holds a key is read off the options schema by its purpose, the way key
  references are.
- The key is asked for once it answers, not on every attempt. OpenSSH 9.8 and
  later shut out an address that keeps connecting without signing in, and
  asking for a key is exactly that. A port nothing listens on yet refuses
  without counting.
- An automatic start fills the home with the sample files a development stack
  seeds into a personal home. They moved from `app/seed_storage.py` to
  `adapters/explorer/samples.py`, so there is one copy, and any source made of
  files can be filled through its own storage.
- The window that says where a service listens shows `ssh://user@127.0.0.1:port`.
  No SSH client takes a password in an address, so the line stays the same when
  the password is handed over. The parts the line is written from are now the
  connector's own fields at the published address, rather than slot names that
  happened to match PostgreSQL's fields.

Rejected: generating the host key here and giving it to the container. The
image reads its keys from its volume, and putting a file there needs either a
bind mount or the archive endpoint of the Engine API. D86 names neither, and
widening the fixed set of calls would buy the checking of a key over a path
that already carries a PostgreSQL password without any check.

Rejected: leaving the key empty and asking the owner to fetch it. The
connection would not work until somebody opened its form, and the fingerprint
they compared would come over the same path the job asks along.

## Left for later

- Signing in to a started server with one of the owner's SSH keys, which the
  old application offered: the public half goes to the image as `PUBLIC_KEY`,
  and the request needs a key id among the things a person may choose (D88).
- FTP and other servers of files, which the explorer is ready for.
