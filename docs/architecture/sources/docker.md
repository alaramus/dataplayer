# Docker

What a Docker source is: a daemon on another machine reached through one of
its owner's SSH connections (D405), the Engine API client it shares with the
managed services (D406), what its catalog shows of containers, images,
volumes, networks and the daemon's reports (D407), what a node opens as
(D408), who may do what and how a refusal is said (D409), a container's
lifecycle (D410), removing, pruning and making volumes and networks (D411),
pull and commit as jobs (D412), a terminal inside a container (D413) and what
changed told as it happens (D414), metrics (D415), search (D416) and a
database's container opened as a connection (D417), a daemon reached
on TCP with mutual TLS (D418) and a container's view of its inspect (D422).
The contract
every source type follows is in [contract.md](contract.md); the SSH tunnel it
rides is D282 in [ssh.md](ssh.md). Read this before changing the `docker`
adapter or `app/adapters/docker_api`.

Decisions here: D405, D406, D407, D408, D409, D410, D411, D412, D413, D414, D415, D416, D417, D418, D422, D423.

## D405. Only a remote daemon, its socket forwarded through an SSH connection

A Docker source is a daemon on another machine. The daemon this server runs
on is never a source, for anybody: a process holding that socket owns the
host, and D86 bounds what this application asks of it to a fixed list. There
is no option, setting or card for it.

The options are the id of one of the owner's SSH connections (required — no
"directly"; the form leaves the empty choice out for a required field) and the
daemon's socket on that machine, `/var/run/docker.sock` by default: an
absolute path, no NUL, no `.` or `..` part, at most 255 bytes. The Podman card
fills `/run/podman/podman.sock`.

The socket is forwarded by the D282 machinery with a second kind of target:
`Tunnels.socket_endpoint` keeps one forwarder per SSH server, account and
socket path, each channel opened as `direct-streamlocal@openssh.com`
(asyncssh's `open_unix_connection`, *checked*, asyncssh 2.24). The owner's
`TunnelAccess` gained `socket_endpoint(connection_id, path)`, answered by an
SSH source through `ForwardsSockets`. The adapter holds no SSH session, and
`asyncssh` stays in the SSH adapter.

The Engine API is spoken over the forwarded port. The check asks `/_ping`
(the body must be `OK`) and `/version`; the session speaks the lower of the
daemon's `ApiVersion` and 1.47, refuses a daemon below 1.41 with a sentence
naming its version, and prefixes every request with `/v1.NN`. A forwarder
closed for idleness comes back on another port, and the session renegotiates
when the port changes.

*Checked* against `docker:29-dind` (Engine 29.10, API 1.57, minimum 1.40) and
OpenSSH 10.3: a missing socket, a socket the account may not open and
`AllowStreamLocalForwarding no` all fail the channel the same way — code 2,
"open failed" — so one sentence names all three, with the path and the user.

Known deviations:

- **"Remote" means through SSH.** An SSH server on the machine this
  application runs on reaches its daemon: that is the person's own account,
  signed into with their own key.
- **No connection string.** The address is the SSH connection's, which a
  Docker source never reads; `DOCKER_HOST=ssh://` would also dial differently
  (`docker system dial-stdio`).
- **No lab and no service.** A daemon started here would be a privileged
  container, which D86 refuses.
- **Podman was not checked yet.** Its card and socket are there; what its
  compatibility API answers differently is still to be listed.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D406. One Engine API client for services and sources

`app/adapters/docker_api` holds what both sides of the API need and nothing
about either: `EngineClient` over a transport factory it is handed, with an
optional `/vNN` prefix; `frames` (the eight-byte multiplexed stream, the text
out of it, a progress stream's failure); `hijack` (a request upgraded to a raw
stream on a byte stream the caller opened). The client raises
`EngineUnreachable` and `EngineRefused(status)`; the daemon's own words go to
the log only. The services hand it an `AsyncHTTPTransport(uds=…)` and keep
their refusal sentences and D86's short list; the source hands it the
forwarded port and has sentences of its own (D409). `services` is above
`adapters` in the layers, so no contract changed.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D407. Containers, images, volumes and networks, and a System section

The top is **System** and four groups. **Containers** holds a folder per
Compose project (the label `com.docker.compose.project`) and **Standalone**,
every container listed running or not and never with `size=true`. **Images**,
**Volumes** and **Networks** list theirs; a network is `built_in` (bridge,
host, none), `compose` (the label `com.docker.compose.network`) or `user`.
How many containers use an image, a volume or a network is counted from the
containers' `ImageID`, `Mounts` and `NetworkSettings.Networks[*].NetworkID`:
the lists leave it out (`Containers: -1` on an image).

Four node kinds: `container`, `image`, `volume`, `network`. A container's
state is one word: `running`, then `healthy`, `unhealthy` or `starting` from
the `Health` field where the API has it and from the status text where it
does not (1.41 lists no `Health`); `stopped` for exit code 0 and `failed` for
any other, read from the status `Exited (n)`; `paused`, `restarting`,
`created`, `removing`, `dead`; anything else `unknown`. The status itself is
kept beside it.

A node is named by what the daemon will not reuse — `container:<64 hex>`,
`image:sha256:<64 hex>`, `volume:<name>` (Docker's own rule,
`[a-zA-Z0-9][a-zA-Z0-9_.-]*`, *checked*), `network:<64 hex>` — matched against
its pattern before any request, and put in the path as one percent-encoded
segment. Each group and project folder opens as a table filtered and sorted
in memory by `app/adapters/listed.py`, the helper Binance's whole lists use.
At most 10,000 of a kind are kept, and the page says when it stopped there.

**System** holds three reports: **Engine** (`/version` and `/info`, named by
the API's own fields; registry mirrors and proxies left out), **Disk usage**
(`/system/df`, asked only when opened, with a two-minute timeout) and
**Events** (the last hour, `until` set so the stream ends, newest first, at
most 2,000).

The catalog has no Copy, Cut or Paste (`catalog_clipboard = False`, D164): a
container, an image, a volume or a network is not rows, and a table of them,
a container's logs or its processes are copied from the grid.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D408. What a node opens as

A container, image, volume or network opens directly as its own node on
the **Overview** view and declares `[view, tree]` (D422). This direct opening
replaces the former catalog expansion in this decision (D423). **As JSON**
opens the daemon's read-only tree (D295) in a tab of its own (D424). Its `DocumentView`
lists the related table pages: a container's **Logs** and **Processes**, an
image's **History**, and a volume's or network's **Containers** (D423). Each
page opens in a separate tab. The node is not a catalog level and its pages are
not rows there; their source-issued IDs still read and resolve through
`path_to`.

Logs are read with `timestamps=true` and `tail` = offset + limit, at most
10,000 lines, and shown newest first as time, stream and text; a container
with `Config.Tty` has one unframed stream, read as stdout; a line is cut at
16 KB. Processes are `/top` with the daemon's own titles as columns; a stopped
container (409) has none and says so.

Known deviations:

- **Inspect shows a container's environment**, which often holds passwords.
  The daemon hands it to whoever reaches the socket; sharing a Docker
  connection with `read` shares that.
- **Logs page by depth, not by time.** The spec's "500 lines before a time"
  became a tail as deep as the page asked, so the grid's own paging works;
  they are not filtered or sorted.
- **A Containers row does not open its container.** The grid's link is a
  relation's foreign key with a predicate; the container is found in the
  catalog. A link in a document view and a search result do open the
  container's preferred view, with its pages (D423). A link in a document view and a search result do open the
  container's preferred view, with its pages (D423). A link in a document view and a search result do open the
  container's preferred view, with its pages (D423).

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D409. Who may do what, and who refused

Three things can refuse and each is said apart. This application's grant
(D33): everything in D407–D408 is `read`. The SSH server or the socket
(D405): the whole connection stops, and the check and every screen say the
sentence. The daemon: a plain one refuses nothing, but an authorization
plugin or a filtering proxy answers 403, said as "The Docker server did not
allow this" with the kind `auth`. 404 on a named node is that node gone; any
other status is "The Docker server could not do that". The daemon's message is
never passed on.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D410. A container's lifecycle is six actions, on containers or a project

Start, Stop, Restart, Pause, Unpause and Kill (`docker/actions.py`) need
`write`, are `bulk`, and act on a container or on a Compose project's folder as
the set of its containers; Standalone is not a project and offers none. Stop
and Restart take an optional wait before killing (0–600 s, empty for the
daemon's default); Kill a signal from `SIGTERM`, `SIGKILL`, `SIGINT`, `SIGHUP`.

Each sorts the containers by their listed `State` into those it acts on, those
already as asked and those it cannot act on, previews that, and runs at once
on the first group; the others are said, not attempted. The daemon is not
trusted to say "already": it answers 304 to a second start or stop, but 409 to
a second pause and 500 to unpausing a running container (*checked*, Engine
29.10). A 304 or 409 during the run — the container changed meanwhile — is
taken as done. The result reloads the project folder and Containers.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D411. Removing says what goes with it; pruning lists what it would take

Remove container, Remove image, Remove volume and Remove network need
`structure`, are `bulk` and destructive, and are judged from what was read
before the daemon is asked:

- a running, paused or restarting container is refused without **Force**; its
  anonymous volumes go only when asked, and its named ones are listed as
  staying;
- an image used by a running container is refused, one used by stopped ones
  needs **Force**, naming them either way;
- a mounted volume is refused naming who mounts it;
- a built-in network is refused, and one with containers names them. The
  daemon answers both with 403 (*checked*), the status a proxy refuses with,
  so they are ruled out first and a 403 after that is the proxy's (D409).

**Prune** is an action of each group's level: stopped containers; untagged
images, or every image no container uses; anonymous volumes (the label
`com.docker.volume.anonymous`, *checked*), or named ones too — before API 1.42
the daemon prunes named volumes whatever it is asked, and the preview says so
by listing them; unused networks other than Docker's three. The preview is
computed here from the lists and the image sizes; the prune itself is the
daemon's and takes what is unused when it runs, which the confirmation says.

**New volume** (driver `local`) and **New network** (driver `bridge`,
internal or not) are actions of Volumes and Networks. A taken volume name is
refused here, because the daemon answers 201 to it and changes nothing.

Known deviations:

- **A set is removed one node per request**, as D9 says for every source; one
  refusal does not stop the rest.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D412. Pull and commit are owned jobs of one target

**Pull image** (on Images) and **Commit to an image** (on a container) need
`structure` and implement `ProducesJob` (D123): the preview carries a
fingerprint of the reference (and the container), the plan is one target, the
unit runs, `observe` reads whether the image or tag is there. A reference is
matched against Docker's grammar first (registry host, lowercase components,
tag, digest), a repository and tag likewise. A pull reads the JSON-lines
stream to its end and fails on an error inside it; 401, 403 or 404 before the
stream is one sentence — not there, or private, and private registries are not
supported (*checked*: a missing or private image answers 404 with "may require
'docker login'"). A pull that loses the SSH link is an unknown outcome.

Known deviations:

- **No layer progress.** A job's progress is its targets (D123), so a pull
  shows one step rather than layers done of layers known.
- **`observe` after a commit** finds the tag, not that this commit made it: a
  tag that existed before reads as done.
- **Creating or running a container** is not planned, as the spec says.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D413. A terminal inside a container is an action whose form opens it

**Terminal** (`docker/terminal.py`) is an action of a container that needs
`own`, as a shell on an SSH server does (D149). Its form chooses the shell from
`/bin/sh`, `/bin/bash`, `/bin/ash` — argv, never a command line — and whether
to run as root rather than the image's user. Instead of running, the form
opens a terminal: the action implements `OpensTerminal`
(`adapters/terminal.py`), `ActionInfo.opens_terminal` is derived from that,
and the terminal socket's first frame (D148) carries the action, the node and
the form. The route asks the source whether the action is offered on that node
before opening anything, so a name in a frame permits nothing (D9). This is the
first terminal on a node rather than on a connection; any source can offer one
the same way.

It is `POST /containers/{id}/exec` with a TTY and `TERM=xterm-256color`,
started over a connection the daemon upgrades (`DockerSession.upgraded`, D406),
resized through `/exec/{id}/resize` — answered 400 until the program has
started, which is let pass — and ended with the exec's exit code. A stopped
container is refused before the daemon's 409. A shell the image lacks still
starts the stream and the daemon prints "OCI runtime exec failed" and exits
127 (*checked*, Engine 29.10); that first line is replaced by a sentence
naming the shell. The terminal's tab is named after the container.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D414. What changed is told while somebody looks, over D303

Docker implements `SupportsChangeWatch` (`docker/watch.py`), and a catalog of
levels now follows too: the level it stands on and the tabs open on the
connection, as a tree follows its open branches. For each open **Logs** tab
the watch reads `follow=true&tail=0` and tells that tab to read again, at most
once every two seconds however fast the container prints. For any level shown
it reads the daemon's `/events` and tells the group an event is about — and a
container's Compose project — for the events that change what a level lists;
a health check's exec, every few seconds, is not one. A stream that drops is
opened again after five seconds.

Known deviations from the spec:

- **A tab is re-read, not appended to.** The spec's own stream of lines,
  1,000 kept and the rest dropped with a count, became the existing D303
  telling: the grid reads its page again, newest first, so nothing is
  dropped and nothing new is drawn on the client.
- **One stream per person and connection, closed by D303's lease** (ninety
  seconds unrenewed) rather than one per container shared by everybody and
  closed ten seconds after the last viewer.
- **The Logs tab still polls every thirty seconds**, for a tab with no catalog
  following beside it.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)


## D415. Running containers are measured from `stats`

Docker implements `SupportsMetrics` (`docker/metrics.py`). A poll reads the
containers and `/containers/{id}/stats?stream=false` of at most 50 running
ones, by name, concurrently; the others are counted in `engine`/`skipped`.
Per container, labelled by its name: `cpu` as `docker stats` says it (the
share of one CPU between the two samples the daemon pairs, above 100 when
several are busy), `memory` less the page cache the kernel may take back
(`inactive_file`, `total_inactive_file` on cgroup v1), `memory_percent` of the
limit, `network_in`/`network_out` summed over interfaces and
`disk_read`/`disk_write` as counters (D127), and `processes`. `engine` counts
running, paused and stopped containers. A container gone between the list and
its `stats` is left out rather than failing the poll. The preset is
**Docker containers**.

*Checked*, Engine 29.10: without `one-shot` the daemon waits about a second to
pair the samples — one second alone, thirty at once in two, inside the poll's
ten — and with it the pair is empty, so the CPU percent could not be read.

Known deviation from the spec: **the skipped are counted, not named** — a
metric is a number, and a name per skipped container would be a series each.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D416. Search reads the four lists once

`docker/search.py` implements `SupportsNodeSearch` and `EnumeratesNames` over
what the catalog reads: containers under their Compose project, the projects
themselves, images by any of their tags (`full_name` holds every tag of an
image with several), volumes and networks. A search starts at the top, in a
group or in a project; a leaf or the System section is refused. Each kept
name is scoped to the level it is listed on. A list past the inventory's
ceiling says the search stopped short. `search_cost` is cheap for names and
costly for anything else, which is not searched.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D417. A database's container opens as a connection of its own type

A source type declares the images its server runs as in its registration:
`register(images=(ContainerImage(repositories, port, options),))`
(`adapters/registry.py`), `options` turning the container's environment into
the type's options other than host, port and tunnel by the image's own
conventions. PostgreSQL (`postgres`, `postgis/postgis`, `pgvector/pgvector`,
`timescale/timescaledb`, `-ha`), MySQL (`mysql`, `mariadb`,
`percona/percona-server`), Redis (`redis`, `redis/redis-stack-server`,
`valkey/valkey`, `bitnami/redis`), MongoDB (`mongo`) and ClickHouse
(`clickhouse/clickhouse-server`, `clickhouse`, over HTTP on 8123) declare
theirs. An image is matched by its repository without tag, digest and Docker
Hub's `docker.io/library/` (`repository_of`); one from another registry is
not matched.

**Open as connection** (`docker/connect.py`) is a `PreparesConnector` action of
a container, offered only where a type declares its image — the menu reads the
container's inspect for it — and requiring `own`, because the draft carries
passwords read from the environment, which an owner already sees in Inspect.
The draft is named after the container and goes through the Docker source's
own SSH connection (`ssh_tunnel`, D282): the server's port published on every
address or on loopback is `127.0.0.1` and that port, one published on another
address is that address, `--network host` is `127.0.0.1` and the port, and
otherwise the container's first network address and the port, as the SSH
server sees them. A stopped container is read from the bindings it asked for.
A password the environment does not hold is left to the form, and the official
Redis image, which takes its password on the command line, drafts no password.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D418. A daemon on TCP with mutual TLS is the second transport

The options are a union on `transport` (`docker/options.py`): `ssh` — the
SSH connection and the socket of D405 — or `tls`: host, port (2376), an
optional `ssh_tunnel` (D282), the CA certificate, the client certificate and
the client key, the key a `SecretStr` (D4). Options stored before the choice
carry no `transport` and are read as `ssh`. Each PEM field keeps the blocks of
its kind, rewrapped at 64 columns, because the form's secret field is one
line and drops the breaks of what is pasted into it; an encrypted key is
refused. The rest of the type does not know which transport it has:
`DockerSession` dials `https://` with an `ssl.SSLContext` built once in a
thread (the client pair written to a private temporary folder, as the
standard library loads a chain only from files, and removed at once), and an
exec's stream opens the same way. The certificate is checked against the
host the options name, not the forwarded port: `EngineClient` takes a
`server_name`, sent as httpx's `sni_hostname`.

**A daemon on TCP without TLS is refused**, and there is no option to allow
one. A handshake that fails for no certificate's reason is followed by one
plain `GET /_ping` on the same address; a daemon that answers it is named in
the refusal. The first exchange also says which part of TLS failed: a
certificate the CA did not sign, a host the certificate is not for, or a
client certificate the daemon refused — under TLS 1.3 that is an
`ssl.SSLError` on the first read, which httpx does not wrap, so
`EngineClient` reduces `OSError` too and keeps the cause for the caller.

**Open as connection** (D417) through a daemon on TLS with no tunnel sees a
container from outside its machine: a port published on every address is at
the daemon's host, and one on its loopback or only a network's address is out
of reach, refused with the port to publish.

*Checked* against `docker:29-dind` with `DOCKER_TLS_CERTDIR` (the `docker-tls`
stand): a client without a certificate fails on
`TLSV13_ALERT_CERTIFICATE_REQUIRED`, a wrong CA and a wrong name on
`SSLCertVerificationError`, and plain HTTP to the TLS port gets a 400.

Known deviation from D405: **a daemon on this server's own machine is not
refused over TLS.** Reaching it takes a client certificate its CA signed,
which only somebody already holding that daemon has; an address cannot be
judged "this machine" reliably behind containers and proxies anyway.

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D422. An inspect opens on its view

A container, image, volume and network declare `[view "Overview", tree
"As JSON"]` on the node itself. The view (D419, [views.md](views.md)) is built
by `docker/card.py` (a container, and the values every Docker view reads
alike) and `docker/cards.py` (the rest) from the inspect the tree reads. The
view's source-owned pages are described in D423.

- **Container.** Header: the name; the state word of D407 read from inspect
  (running and healthy `good`, starting, restarting and removing `busy`,
  unhealthy, failed and dead `bad`, paused `warning`, stopped, never started
  and unknown `neutral`); the image as a link. Sections: Overview — id,
  created, started (running) or finished and exit code, restart policy and
  count, command and entrypoint as code, working directory, user, the Compose
  project as a link to its level and the service; Health, only when a check is
  defined or reported — status, failing streak, the check, the last results
  newest first; Network — the mode, published ports one row per address, the
  networks with address and gateway as links; Storage — mounts, a volume as a
  link; Environment — pairs, sensitive by name (D421: `PASSWORD`, `PASSWD`,
  `SECRET`, `TOKEN`, `KEY`, `CREDENTIAL`, `PRIVATE`, case-folded); Labels —
  collapsed; Resources — memory, CPUs and processes, `empty` when the daemon
  says 0. Notices above: killed for memory, more than three restarts.
- **Image.** Tags as chips, id, size, created, platform, entrypoint, command,
  working directory, user, exposed ports, the layers counted as a link to its
  History; the containers that run it with their state; environment; labels.
- **Volume.** Driver, mount point, scope, created; the containers that mount
  it, their state, where and whether writable; options; labels.
- **Network.** Id, driver, scope, internal, attachable, IPv6, created; the
  subnets, gateways and ranges; the containers on it with IPv4, IPv6 and MAC
  as its inspect names them; options and labels, collapsed.
- **What changed is told** (on D414). An open view's node — the leaf or its
  Inspect — is followed like a level: `/events` is opened for it alone if no
  level is shown, and `views_told` names the views an event is about. A
  container's event tells its view, and every image and volume view shown,
  since they list container states; a network's connect or disconnect tells
  the network and the container; an image's tag, untag or delete tells that
  image, and a pull — which names a reference, not an id — every image view;
  a volume's create, destroy, mount or unmount tells that volume. A health
  check's exec is not an event any view shows.

Docker's `created` state is worded "never started": the English key
"created" is shared with another package, whose Russian is feminine.

Known deviations:

- **An image's and a volume's view read the container list too**, one request
  beside the inspect: who uses them is not in their inspect, and is counted
  from the containers as the levels count it (D407). A network's inspect
  names its own containers.
- **A view is told only while a catalog of the connection is open.** The
  watch is held by the catalog panel (D303), as a Logs tab's is.

Spec: [A view of a document](../../decisions/2026-11-21-document-views-design.md)

## D423. Docker nodes open directly and advertise their pages

Containers, images, volumes and networks are catalog leaves. Clicking one
opens its first representation, the **Overview** view; its tab uses the node's
name. The old level that listed Inspect and the table pages is gone. Catalog
actions on these nodes keep their existing targets and menu.

The source adds `pages` to the `DocumentView` response. Each page carries its
source-issued `node_id`, localized `title` and ordered `representations`. The
client draws a button for each page in the view header and opens its preferred
representation in a separate tab named `<node> — <page>`. The view and **As
JSON** still replace each other in the same tab through `switchRepresentation`
(D419); the client has no Docker-specific branch.

Docker advertises Logs and Processes for a container, History for an image,
and Containers for a volume or network. `list_children` validates a Docker
node and returns no catalog rows, while these child IDs remain valid for row
fetches and `path_to`. Search and links resolve to the node's own preferred
representation, so they open the same view with the same page buttons. The
existing D414 IDs keep the log stream and the card event refresh working.

Spec: [Docker node pages and opening](../../decisions/2026-11-21-docker-node-pages-design.md)
