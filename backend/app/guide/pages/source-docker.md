# Docker

A Docker daemon on another machine, reached through one of your SSH
connections or over TCP with TLS. You see its containers, images, volumes and networks, what the
daemon says about each, a container's logs and processes, and the daemon's
own reports. How connections work in general is on the
[Connections](connections.md) page.

## What you can see

- Containers, grouped by Compose project, running or not
- Images, volumes and networks, and which containers use each
- What the daemon says about any of them, as a JSON tree
- A container at a glance, its secrets hidden until asked for
- A container's logs as they are written, and the processes in it
- An image's layers and the instructions that made them
- The engine: versions, drivers, CPUs, memory, disk usage, recent events
- Running containers' CPU, memory, network and disk on a dashboard

## What you can change

- Containers started, stopped, restarted, paused, unpaused or killed
- A Compose project's containers, all at once
- Containers, images, volumes and networks removed
- Stopped containers and unused images, volumes and networks pruned
- New volumes and networks
- Public images pulled, and a container committed to an image
- A shell inside a running container, in a terminal
- A database's container opened as a connection of its own

## Connecting

**Transport** chooses how the daemon is reached: **Socket through SSH** or
**TCP with TLS**, below. For the socket, make an **SSH connection** to the
machine the daemon runs on first; then the **Connection** page asks for:

- **SSH connection**: one of your SSH connections. Its account must be allowed
  to use the daemon's socket — on most machines, it is in the `docker` group;
- **Socket**: where the daemon listens on that machine. `/var/run/docker.sock`
  for Docker; `/run/user/<uid>/docker.sock` for rootless Docker. The
  **Podman** card fills in `/run/podman/podman.sock`; a rootless Podman uses
  `/run/user/<uid>/podman/podman.sock`, and its socket must be switched on
  (`systemctl --user enable --now podman.socket`).

The socket is forwarded through the SSH connection, the way a database is
reached through an SSH tunnel; the SSH server must allow it
(`AllowStreamLocalForwarding`, on by default). If the check says the socket
could not be opened, one of three things is wrong, and OpenSSH does not say
which: nothing listens at that path, the account may not use it, or the
forwarding is switched off.

The daemon must speak API 1.41 or newer (Docker 20.10 and later).

The Docker daemon of the machine DataPlayer itself runs on is never offered:
whoever holds that socket holds the machine.

## Over TCP with TLS

A daemon that listens on TCP with mutual TLS — `dockerd --tlsverify`, usually
on port 2376 — is reached without SSH. The form asks for:

- **Host** and **Port**: as the daemon's certificate names the host;
- **CA certificate**: `ca.pem`, the authority that signed the daemon's;
- **Client certificate** and **Client key**: `cert.pem` and `key.pem`, which
  the daemon accepts. The key must not be encrypted.

Paste each file whole, `-----BEGIN` line and all. **SSH tunnel** stays
**Directly** unless the port is reachable only from inside another network;
then the host is the name the SSH server reaches it by.

A daemon on TCP without TLS — port 2375 — is refused, and the check says so:
whoever reaches that port owns the machine. The check also says which part
failed: a certificate not signed by the CA, a host the certificate is not for,
or a client certificate the daemon does not accept.

## The catalog

- **System** holds the daemon's reports, below.
- **Containers** holds one folder per Compose project, named by the label
  Compose writes, and **Standalone** for the rest. Each container shows its
  state in one word with the daemon's status, image, Compose service and
  published ports beside it.
- **Images** lists every image by its id, tagged or not, with its size and how
  many containers use it. **Volumes** lists every volume by name; **Networks**
  lists each network, Docker's own three first, marked built-in, Compose or user.
- Each group opens as a table too, which can be filtered and sorted by any
  column. More than ten thousand of a kind are not listed.
- Clicking a container, image, volume or network opens its overview directly in
  a tab named for that node. It does not open another catalog level. Node
  actions remain in the catalog menu.

## What a node opens as

- Click a container to open its overview in a tab named for the container:
  its state, image, creation and start or exit, restart policy and count,
  command, health check and recent results, ports, networks and addresses,
  mounts, environment, labels and resource limits. A notice says when it
  restarted more than three times or was killed for running out of memory.
- **As JSON** switches that same tab to the daemon's read-only tree, and the
  overview switches it back. The image, volume, network and Compose project in
  the card are links; opening one shows its own overview.
- The card's **Logs** and **Processes** buttons open separate table tabs named
  for the container and page, such as `dp-test-web — Logs`. Logs show time,
  stream and text, newest first, up to ten thousand lines; each line is cut at
  16 KB. Processes show what runs now; a stopped container has none.
- An image's **History** button opens its layers in a separate tab. A volume's
  or network's **Containers** button opens the containers that use it, also in
  a separate tab. The overview tab keeps the node's name.
- A card opened from search or a link has the same page buttons. An open card
  reads itself again when the daemon reports a change to what it shows, while
  a connection catalog is open.
- A variable whose name holds PASSWORD, PASSWD, SECRET, TOKEN, KEY,
  CREDENTIAL or PRIVATE is shown as dots until you press its eye, and is copied
  only once shown. That hides it from a glance, not from a reader: the JSON
  shows it plainly, and anybody you share this connection with sees a
  container's environment.

## The System section

- **Engine**: the daemon's versions, operating system, kernel, drivers,
  CPUs, memory and counts of containers and images, by the daemon's own
  names. Registry mirrors and proxies are left out: they can hold passwords.
- **Disk usage**: every image, container, volume and build cache entry with
  its size, and whether removing it would free space. The daemon sizes every
  volume to answer, so it can take a while.
- **Events**: what happened in the last hour, newest first.

## When something is refused

- The SSH connection or the socket refusing stops the whole connection, and
  every screen says why.
- A daemon behind an authorization plugin or a filtering proxy may refuse one
  request: that is said as **The Docker server did not allow this**.

## Changing things

Select a container, a Compose project folder or a node and open the catalog's
menu. Starting, stopping and the rest of a container's lifecycle need write
access; removing, pruning, pulling, committing and making volumes and networks
need structure access.

- **Start**, **Stop**, **Restart**, **Pause**, **Unpause** and **Kill** act on
  the selected containers, or on every container of a selected Compose
  project. Each first lists what it would do and which containers are already
  so. Stop and Restart can wait a number of seconds before killing; Kill sends
  the signal you choose.
- **Remove container** refuses a running one unless **Force** is ticked, and
  can take its anonymous volumes with it. **Remove image** names the
  containers that use it; **Remove volume** refuses one a container mounts;
  **Remove network** refuses one with containers on it, and Docker's own three.
- Inside **Containers**, **Images**, **Volumes** and **Networks**, **Prune**
  lists what would go and, for images, the space it frees. The daemon prunes
  whatever is unused when you press it, so something that stopped being used
  meanwhile goes too.
- **New volume** and **New network** are in **Volumes** and **Networks**.
- **Pull image** in **Images** and **Commit to an image** on a container run
  as jobs in **Activity**. Only public images can be pulled: a registry that
  asks for a sign-in is said to be unsupported.

## A terminal inside a container

Select a running container and choose **Terminal** in the catalog's menu.
Choose the shell — `/bin/sh` is in almost every image, `/bin/bash` and
`/bin/ash` in some — and whether to run it as root rather than as the image's
user. The shell opens in **Terminals** at the foot of the window, named after
the container, and ends when you close it. Only the owner of the connection
can open one: whoever you share it with cannot. A container without the shell
you chose says so; open it again with another.

## Logs and levels that keep up

While a container's **Logs** is open, new lines appear as the container prints
them, at most every two seconds. The level you stand on in the catalog reads
itself again when the daemon changes it: a container that stops, an image
pulled, a volume removed — by DataPlayer or by anybody else.

## Metrics on a dashboard

Switch on reporting for the connection, then add the **Docker containers**
layout to a dashboard. Each poll measures up to fifty running containers, by
name: CPU — 100% is one CPU fully busy, so it can pass 100% — memory without
the cache the system can take back, network and disk traffic per second, and
the processes in each. It also counts running, paused and stopped containers;
**Containers not measured** counts the running ones past the fifty. A poll
takes about a second: the daemon measures each container twice to tell its
CPU use.

## Search

The catalog's search and the search over everything find containers, Compose
projects, images by any of their tags, volumes and networks by name. Inside a
folder, the search looks in that folder only.

## A database's container as a connection

Select a container of PostgreSQL, MySQL, MariaDB, Redis, MongoDB or ClickHouse
and choose **Open as connection**. A new connection form opens, filled in from
the container:

- the same SSH connection, as its SSH tunnel;
- the published port at `127.0.0.1`, or else the container's own address;
- the user, password and database the container was started with.

Check it and save. An image is recognised by its name on Docker Hub, such as
`postgres` or `mariadb`; one from another registry is not. The official Redis
image takes its password on its command line, so type it in. Only the owner of
the Docker connection can do this, because the form carries the container's
passwords.

## What Docker does not have here yet

- Private registries, and creating or running new containers
