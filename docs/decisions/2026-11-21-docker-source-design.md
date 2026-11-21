# A Docker source

Decisions D405–D418. A source type that looks at and manages a Docker daemon
on another machine: its containers, images, volumes and networks, a
container's logs and processes, the daemon's own reports, and — in later
slices — changing state, a terminal inside a container, live logs, metrics
and a container opened as a connection of its own type. The whole plan is
here; each slice is implemented and committed on its own, and when a slice
finds a fact that changes a decision, the architecture file records the new
reasoning (this spec stays as written).

Facts marked *to check* were not tried when this was written. Every one of
them is probed in a scratch script against the test stand (below) before the
slice that depends on it, and marked *checked* with the version in the
architecture file. Read [adding-a-source.md](../architecture/sources/adding-a-source.md)
first: its six slices do not fit a source without SQL, rows to edit or
columns to change, so this plan has its own five, but its "every slice" and
"once per type" lists still apply.

## Only a remote daemon, reached through an SSH connection (D405)

A Docker source is a daemon on another machine. **The daemon this server runs
on is never a source**, for anybody, superusers included. A process holding
that socket owns the host it runs on, and D86 bounds what this application
asks of it to a short fixed list a proxy can enforce; a source that browses,
stops and removes containers would end that promise, and would let one click
stop the backend serving the click. There is no option, setting or card for
it.

The daemon is reached through **one of its owner's SSH connections**, named by
id the way a database names its tunnel (D282), not through SSH fields of its
own: the server key is pinned once (D145), keys and passphrases are the
person's (D146, D147), and replacing a key is one edit. The SSH connection
must be the owner's, switched on and of type SSH; a grantee reads through it
without being able to open it (D33).

**The daemon's socket is forwarded, and the Engine API is spoken over it.**
The alternative — running `docker …` over the SSH session and reading what it
prints — was rejected:

- a command line is a string, and every container name, image reference and
  filter would have to be quoted into it correctly forever (D2c, D144);
- the CLI prints for people: sizes as `867MB`, times as "3 hours ago", tables
  whose shape changes between versions; the API answers JSON with bytes and
  timestamps;
- the CLI need not be installed where the daemon is, and its version is not
  the daemon's.

The forwarding is the D282 machinery with a second kind of target: `Tunnels`
in `adapters/ssh/tunnel.py` keeps one forwarder per SSH server, account and
target, and a target may now be **a Unix socket path on the SSH server**,
opened as a `direct-streamlocal@openssh.com` channel (asyncssh's
`open_unix_connection`, *to check*). `TunnelAccess` gains
`socket_endpoint(connection_id, path) -> (host, port)`, a port on
`127.0.0.1`. The Docker adapter never holds an SSH session, and `asyncssh`
stays in its adapter (`lint-imports`).

Options:

- **SSH connection** — required; an empty choice is a validation error, not
  "directly".
- **Socket** — the daemon's socket on that machine, default
  `/var/run/docker.sock`. An absolute path, no NUL, no `..` segment, at most
  255 bytes; checked by pattern. Rootless Docker is
  `/run/user/<uid>/docker.sock`, Podman `/run/podman/podman.sock` or
  `/run/user/<uid>/podman/podman.sock`; the cards and the guide say so.

**The API version is negotiated, with a floor.** The check asks `GET /_ping`,
then `GET /version`; the adapter uses the lower of the version it is written
for and the daemon's `ApiVersion`, refusing a daemon below **1.41** (Docker
20.10) with a sentence naming the daemon's version. Every request is prefixed
`/v1.NN`. Docker 29 refuses clients below 1.44 (*to check*) and Podman's
compatibility API reports 1.41 (*to check*), so the client is written to work
at 1.41 and uses nothing newer without asking the version first.

**Podman is a card of this type** (D264): same API, its socket path, its own
icon. What Podman answers differently is found on the test stand and listed
as known deviations, the way D378 lists TiDB's.

What the SSH server can refuse, and the sentence for each (*to check* how
OpenSSH tells them apart on a failed channel open; if it does not, one
sentence names all three):

- socket forwarding switched off (`AllowStreamLocalForwarding no`);
- no such socket — Docker not installed or not running, or another path;
- permission denied — the SSH user is not in the `docker` group; the sentence
  names the user and the group.

A connection string is the SSH connection's address with the socket as its
path, `ssh://user@host:port/var/run/docker.sock`, never a password (D89). It
is shown, not dialled: Docker's own `DOCKER_HOST=ssh://` runs
`docker system dial-stdio` on the far side, which this source does not.

Known deviations:

- **"Remote" means through SSH.** An SSH server on the very machine this
  application runs on reaches its daemon; that is the person's own account on
  that machine, signed into with their own key, and nothing here can tell a
  host from itself.
- **No lab and no service.** A Docker daemon started here would be a
  privileged container, which D86 refuses.

## One Engine API client for services and sources (D406)

`services/docker.py` already speaks the Engine API with httpx over a Unix
socket: requests with timeouts, the daemon's status codes reduced to
sentences, the 8-byte multiplexed stream taken apart, a hijacked connection
for a console. `services` sits above `adapters`, so the adapter cannot import
it, and a second client of the same API is the duplication ENGINEERING.md
forbids.

The transport-neutral part moves below both, to `app/adapters/docker_api/`
(a package of shared pieces, not a source type; *to check* that the layer
contract admits `services` importing it): a client built on an httpx
transport it is handed, the version prefix, the refusal table, the stream
demultiplexer, the reader of JSON-lines progress streams, and opening a
hijacked connection given a function that opens a byte stream. Services hand
it `AsyncHTTPTransport(uds=…)` and `unix_connection`; the source hands it
`http://127.0.0.1:<forwarded port>` and `asyncio.open_connection`. What each
side asks for stays its own: D86's short list is still the only thing the
services module calls.

The move is the first commit of the first slice, with the services' tests
green before anything new is written on top.

## Containers, images, volumes and networks, and a System section (D407)

The catalog's top level is four groups and the reports:

- **Containers**, grouped by Compose project (the label
  `com.docker.compose.project`), the rest under **Standalone**. A container
  shows its name, state, image, ports, created and started times, and its
  project and service. Every container is listed, running or not
  (`all=true`); sizes are not asked (`size=true` makes the daemon walk every
  container's filesystem).
- **Images** — one node per image id, its tags (`<none>` for an untagged
  one), size in bytes, created, and how many containers use it, counted from
  the containers' `ImageID`.
- **Volumes** — name, driver, mountpoint, created, labels, and the containers
  that mount it, from the containers' `Mounts`.
- **Networks** — name, driver, scope, internal, and a kind: *built-in* for
  `bridge`, `host` and `none`, *Compose* when the label
  `com.docker.compose.network` is set, *user* otherwise; the containers on it
  are counted from the containers' `NetworkSettings.Networks`, since the list
  of networks leaves them empty.

**A container's state is one word read from three fields**, with the raw
status beside it: `running`; `healthy`, `unhealthy` or `starting` when it has
a health check; `paused`; `restarting`; `stopped` for an exit code of 0;
`failed` for any other; `created`; `dead`. An unknown status passes through
as it is rather than being guessed.

**A node is named by what the daemon will not reuse**: a container and a
network by their 64-hex id, an image by `sha256:<64 hex>`, a volume by its
name (Docker's rule, `[a-zA-Z0-9][a-zA-Z0-9_.-]*`, *to check*). Every id from
a client is matched against its pattern before a request is built, and goes
into the URL as a percent-encoded path segment, never concatenated. A
container renamed while a tab is open is still the same node.

**Lists are whole, and bounded.** The API does not page; the adapter reads at
most 10,000 of a kind and says when it stopped there (D2d). Filters and
sorting of a level are the closed predicates of every source, applied to the
list in memory.

**The System section** holds reports read like tables (D55):

- **Engine** — `/version` and `/info`: versions, API version, operating
  system, kernel, architecture, storage and logging drivers, cgroup version,
  rootless, security options, CPUs and memory, counts of containers by state
  and of images. Registry mirrors and proxies are left out: they can carry
  credentials in their URLs.
- **Disk usage** — `/system/df`: images, containers, volumes and build cache,
  each with its size and what could be reclaimed. Asked only when the report
  is opened; it is the one slow call (*to check* how slow on a host with many
  volumes).
- **Events** — `/events` for the last hour, newest first: time, type, action,
  the object and its name.

## What a node opens as (D408)

Each node has more than one representation (D47):

- **Inspect** — the daemon's JSON for the object, as a read-only tree (D295).
- A container's **Logs** — rows of time, stream (`stdout`, `stderr`) and text,
  newest first, a page being the 500 lines before a time (`tail` and `until`,
  `timestamps=true`). A container with a TTY has one unmultiplexed stream
  (`Config.Tty`), read as `stdout`. A line is cut at 16 KB.
- A container's **Processes** — `/containers/{id}/top` as rows; a stopped
  container says it has none.
- An image's **History** — its layers as rows: created, the instruction, size.
- A volume's and a network's **Containers** — who mounts or is attached, as
  rows that open the container.

Known deviations:

- **Inspect shows a container's environment**, which often holds passwords.
  Docker hands it to anybody who reaches the socket; sharing a Docker
  connection with `read` is sharing that, and the sharing window says so.

## Who may do what, and what the daemon refuses (D409)

Three different things can say no, and a person is told which one did:

1. **This application, by the grant** (D33). Every action declares the level
   it needs: `read` for everything in D407–D408; `write` for start, stop,
   restart, pause, unpause and kill; `structure` for remove, prune, pull,
   commit and making a volume or a network; `own` for a terminal inside a
   container and for the connection itself. As everywhere (D79), an action
   above the grant is not offered and is refused by the route.
2. **The SSH server or the socket** — the sentences of D405. This stops the
   whole source, not one button, and it is said by the check and by every
   screen's failed read.
3. **The daemon.** A plain daemon refuses nothing to whoever reached its
   socket; a careful installation puts an authorization plugin or a filtering
   proxy in front of it, which answers 403. That is said as "The Docker
   server did not allow this", with the action named. The daemon's own
   message is not passed on — it names host paths and digests (D82's rule,
   the services' refusal table reused) — except the closed set of reasons the
   adapter recognises itself, below.

Every other refusal is reduced by status and by what the adapter checks
first: 404 is a node that is gone; 409 on removal is "it is running — stop it
first, or remove it with Force"; 409 on an image is "containers use it", with
their names, which the adapter already knows; 304 is "it is already in that
state".

## Slice 1 — read only

D405–D409, the user's guide page in every locale (D183) with the Docker and
Podman cards, and the test stand:

- `deploy/docker-remote/`: one image with `dockerd` and `sshd`, a user
  `dataplayer` in the `docker` group, socket forwarding allowed. A compose
  service `docker-remote` under the `tools` profile, `privileged` (as every
  Docker-in-Docker is), its SSH port published on loopback. CI runs the same
  image as a service with `--privileged` (*to check* that GitHub's services
  accept it).
- Backend tests that need it go through `tests/utils/services.py` and skip
  without it. Everything else — states, kinds, counts, the refusal table,
  version negotiation, id patterns — is tested against `httpx.MockTransport`
  answers recorded from the stand.
- Podman is checked by hand once against `quay.io/podman/stable`, and what
  differs is written down; it is not in CI.

## Changing state (D410–D412, slice 2)

**D410. A container's lifecycle is six actions.** Start, stop (with the
daemon's default timeout, and a field for another), restart, pause, unpause,
kill (signal from a closed list: `SIGTERM`, `SIGKILL`, `SIGINT`, `SIGHUP`).
Each acts on one container or on a set of them (D68), and on a Compose
project as the set of its containers. Each answers what it would do (D46) —
which containers, which are already in that state — and runs at once; none is
a job.

**D411. Removing is reviewed and counted.** Remove a container (Force for a
running one; Remove its anonymous volumes as a choice), an image (Force; the
containers using it named), a volume (refused while mounted, naming who), a
network (refused while anything is attached; built-in ones never). **Prune**
is an action of each group — stopped containers, dangling or all unused
images, unused volumes, unused networks — and its preview is the list the
adapter computes from what it has read, with the space it frees where known.
The prune call itself is the daemon's; something made between the preview and
the call can be pruned too, which the window says. Whether volume prune
removes named volumes depends on the API version (`all` filter since 1.42,
*to check*); the preview follows the same rule.
Making a **volume** (name, driver `local`) and a **network** (name, driver
`bridge`, internal) are actions of their groups.

**D412. Pull and commit are jobs.** Pull takes an image reference matched
against Docker's reference grammar and is a job (D81) whose progress is the
daemon's JSON-lines stream reduced to layers done of layers known; an error
inside a `200` stream fails the job. **Only public images in this plan**:
a registry that asks for sign-in fails with a sentence saying private
registries are not supported yet. Commit makes an image from a container
(repository and tag, validated the same way) and is a job too, since a large
container takes minutes.

Not planned: creating or running a container. A form for `docker run` is a
product of its own; Compose is a client-side program the Engine API knows
nothing of.

## A terminal and live logs (D413–D414, slice 3)

**D413. A terminal inside a container is its owner's.** It is the terminal
socket of D148, owned and lived as D149 says, with `own` required. The
program is chosen from a closed list — `/bin/sh`, `/bin/bash`, `/bin/ash` —
as argv, never a shell string; it runs as the image's user, or as `root` when
that is chosen. It is `POST /containers/{id}/exec` with a TTY, started over a
hijacked connection to the forwarded port (D406), resized through
`/exec/{id}/resize`. An image with no shell says so instead of a dead screen.

**D414. Live logs are a topic.** A container's Logs view can follow: one
`follow=true` stream from now per container while anybody watches, published
on a topic (D18), closed ten seconds after the last viewer leaves. The client
keeps the last 1,000 lines; a container printing faster than the screen can
draw has lines dropped with a count shown, never a stalled stream.

## Metrics, search and a container as a connection (D415–D417, slice 4)

**D415. Metrics from `stats`.** The connection poll (dashboards) reads
`/containers/{id}/stats?stream=false` for running containers — CPU percent
from the delta the daemon pairs in `precpu_stats`, memory used and limit,
network and block I/O — at most 50 containers a poll, concurrently, the rest
counted as skipped (*checked*, Engine 29.10: without `one-shot` the daemon
waits about a second to pair samples, thirty containers at once take two; with
it the pair is empty and the CPU percent cannot be read).

**D416. Search** enumerates names (`EnumeratesNames`): containers, image
tags, volumes, networks, and the Compose projects; `SupportsNodeSearch` over
the same lists.

**D417. A container opens as a connection of its own type.** A source type
may declare the images it runs as (`postgres`, `mysql`, `redis`, …) in its
own registration (D1, D13), so no list kept here drifts from the types. A
container whose image matches offers **Open as connection**: a draft of that
type through **the same SSH connection** as its tunnel (D282), the host the
container's address on its network as the SSH server sees it, or `127.0.0.1`
and the published port when it publishes one. Credentials are read from the
container's environment by the conventions the target type declares
(`POSTGRES_PASSWORD`, …); a draft carrying them requires `own`, like any
draft filled from credentials.

## TLS without SSH (D418, slice 5)

A daemon listening on TCP with mutual TLS (port 2376) is the second transport:
host, port, a CA, a client certificate and its key as PEM, the key a
`SecretStr` (D4); optionally through an SSH tunnel (D282) like any address.
**A daemon on TCP without TLS is refused** — a form cannot make one safe, and
whoever reaches port 2375 owns that host. The form chooses the transport
first, and the rest of the type does not know which one it has.

## Not planned

- **Files inside a container or a volume.** The archive API returns a whole
  folder as a tar, so listing a large folder would download it; listing
  through `exec` would be a command this source runs. Revisit if wanted.
- **Swarm services and stacks, builds, Kubernetes.**
- **Private registries** — see D412.
