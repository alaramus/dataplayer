# Docker

What a Docker source is: a daemon on another machine reached through one of
its owner's SSH connections (D405), the Engine API client it shares with the
managed services (D406), what its catalog shows of containers, images,
volumes, networks and the daemon's reports (D407), what a node opens as
(D408), who may do what and how a refusal is said (D409), a container's
lifecycle (D410), removing, pruning and making volumes and networks (D411),
and pull and commit as jobs (D412). The contract
every source type follows is in [contract.md](contract.md); the SSH tunnel it
rides is D282 in [ssh.md](ssh.md). Read this before changing the `docker`
adapter or `app/adapters/docker_api`.

Decisions here: D405, D406, D407, D408, D409, D410, D411, D412.

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

Spec: [2026-11-21-docker-source-design.md](../../decisions/2026-11-21-docker-source-design.md)

## D408. What a node opens as

A container, image, volume or network is walked into, and holds its views:
**Inspect** first, the daemon's JSON for it as a read-only tree (D295), then
tables — a container's **Logs** and **Processes**, an image's **History**, a
volume's and a network's **Containers**. Opened from elsewhere — a search, a
link — the node itself still answers as its Inspect tree. Walked rather than
opened because a node that opens and holds nodes opens as a workbook does
(D51), and that tab offers only sibling tables: the logs were out of reach.

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
  catalog.

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
