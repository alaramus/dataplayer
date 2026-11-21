# Docker

A Docker daemon on another machine, reached through one of your SSH
connections. You see its containers, images, volumes and networks, what the
daemon says about each, a container's logs and processes, and the daemon's
own reports. How connections work in general is on the
[Connections](connections.md) page.

## What you can see

- Containers, grouped by Compose project, running or not
- Images, volumes and networks, and which containers use each
- What the daemon says about any of them, as a JSON tree
- A container's logs as they are written, and the processes in it
- An image's layers and the instructions that made them
- The engine: versions, drivers, CPUs, memory, disk usage, recent events

## What you can change

- Containers started, stopped, restarted, paused, unpaused or killed
- A Compose project's containers, all at once
- Containers, images, volumes and networks removed
- Stopped containers and unused images, volumes and networks pruned
- New volumes and networks
- Public images pulled, and a container committed to an image
- A shell inside a running container, in a terminal

## Connecting

The daemon is never reached directly. Make an **SSH connection** to the
machine it runs on first, then the **Connection** page of a Docker connection
asks for:

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

## The catalog

- **System** holds the daemon's reports, below.
- **Containers** holds one folder per Compose project, named by the label
  Compose writes, and **Standalone** for the rest. Each container shows its
  state in one word — running, healthy, unhealthy, starting, paused,
  restarting, stopped, failed, created or dead — with the daemon's own status
  beside it, its image, its Compose service and its published ports.
- **Images** lists every image by its id, tagged or not, with its size and
  how many containers use it.
- **Volumes** lists every volume by name; **Networks** every network, Docker's
  own three first, each marked built-in, Compose or user.
- Each of these folders opens as a table too, which can be filtered and
  sorted by any column. More than ten thousand of a kind are not listed.

## What a node opens as

- A container, an image, a volume or a network opens as what the daemon says
  about it, as a JSON tree. A container's includes its environment, which
  often holds passwords: anybody you share this connection with sees it.
- Inside a container: **Logs** — the time, the stream (stdout or stderr) and
  the text of each line, newest first, as far back as ten thousand lines, a
  line cut at 16 KB — and **Processes**, what runs in it now. A stopped
  container has none.
- Inside an image: **History**, its layers.
- Inside a volume or a network: **Containers**, the ones that use it.

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

## What Docker does not have here yet

- Metrics on a dashboard, and search
- A daemon reached over TLS rather than SSH
- Private registries, and creating or running new containers
