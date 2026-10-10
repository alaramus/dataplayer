# Monitor agent protocol: receiving what dataplayer-monitor-agent sends

## Outcome

The `metrics` process receives only DPMA/1, the protocol of
`dataplayer-monitor-agent` (repository `github.com/alaramus/dataplayer-monitor-agent`,
image `alaramus/dataplayer-monitor-agent`, its `PROTOCOL.md`). Every datagram is
checked before it is read and written as it was sent. What `sys_monitor_agent`
sent is not read any more, and what it wrote is taken out of the store.

A person sees the new agent's hosts in the Sources window — what system each
is, its processors and memory, the agent's version — starts one from the
Compose file shown there, and gets a *Linux host* layout built on the new
metrics: CPU by mode and per core, memory, load, network, disk I/O, file
systems, TCP connections, containers and the top processes with their state,
resident size and start.

## Evidence

- `sys_monitor_agent` 1.14.0, measured on 2026-09-13: network and CPU measured
  since the agent started, network divided by an interval of 30 or 31 seconds,
  only the first core read, a crash every 33 seconds with `iftop`, the key in
  every packet in plain text, no version, start or sequence. D130 was written
  around those facts; most of what it describes was guessing.
- The new agent was run on Docker Desktop against a receiver on 2026-09-13:
  65 datagrams, none refused, sequence in order, the largest 1386 bytes, 142
  samples per round, a process table in two parts.

## What changes

### Receiving (D127, D130)

- **A datagram is `DPMA/1 <kid> <signature>\n<body>`.** The key id is the first
  16 hexadecimal characters of the key's SHA-256, which is how the application
  database already looks a key up, so no column is added. The metrics process
  holds the keys themselves, unsealed, because an HMAC is checked with the key;
  a key id matching several agents tries each.
- **Checked in order, each refusal counted apart:** a frame that is not DPMA/1,
  a key id nobody holds, a signature that does not match, a body that is not
  the protocol, a time more than ten minutes old or two minutes ahead, a
  sequence number already accepted for that agent instance.
- **A body is refused whole** when any sample or row in it breaks the protocol.
  The agent checks each sample before it packs it; a datagram that still
  carries a bad one is a defect to be seen, not data to be salvaged.
- **Samples are written as they come.** No unit table, no counters turned into
  increments, no label guessing: `packets.py`, `units.py` and the agent half of
  `counters.py` go. Connections keep their rates (D127).
- Accepted sequence numbers are remembered per agent instance, a window of 1024
  below the highest, and forgotten a quarter of an hour after the instance was
  last heard: a replay older than that fails the time check anyway.

### Restarts (D130)

- **A restart is a new `agent.instance`.** Its moment is `agent.started`; its
  cause is `host` when `host.boot` changed with it and `agent` otherwise. An
  instance that started earlier than the one already known is an older process
  still sending, or a second agent reporting the same host name, and is not a
  restart.
- The newest instance of every host is kept in the store, so a restart of the
  metrics process does not forget what it had seen.
- Three restarts of one host in fifteen minutes stay the attention item they
  were. The `iftop` hint goes with `iftop`.

### What the store keeps (D126)

- **`metric_host`**, one row per agent and host: the instance, its version and
  start, the boot id, and the last `host` description — operating system,
  kernel, architecture, processors, memory, boot time and the collectors with
  their intervals.
- **`metric_process` is made again** with the protocol's columns: state,
  resident size, start and executable name beside PID, parent, user, CPU,
  memory and command, and the host's total process count. A table sent in
  parts is the rows of every part at one moment.
- **Migration 4 takes out everything agents wrote**: their series, points,
  rollups, processes and restarts. Connections' series stay. A widget naming a
  series that is gone says so, and its owner removes it.

### Screens (D128, D129)

- The Sources window lists the hosts of the person's agents, with the
  description above and when each was last heard.
- The Compose file is the new image with the host's `/proc`, `/sys` and `/`
  mounted read-only, its process and network namespaces, the Docker socket
  read-only, `DPM_SERVER` and `DPM_KEY`. The host name is the host's own unless
  one is typed.
- The process table shows state, resident size and start, and says how many
  processes the host has.
- *Linux host* is rewritten for the protocol's metrics; no recipe spans units.
- Development's `monitor-agent` profile runs the new image against the stack.

## Rejected

- **Keeping the old format beside the new one.** Two interpreters, and a store
  holding numbers that mean different things under similar names. There is no
  installation whose agents cannot be replaced.
- **Taking widgets off dashboards in the same migration.** The store's migration
  cannot reach the application database, and a series gone from under a widget
  is already what purging an agent does.
- **Verifying against the fingerprint without the key.** An HMAC needs the key;
  a signature over a hash of the key would make that hash the secret, and it is
  stored in the clear.

## Slices

| Slice | Contents |
| --- | --- |
| MA1 | DPMA/1 in the metrics process: frame, key, signature, body, freshness; restarts from instance and boot; `metric_host` and the new `metric_process`; migration 4; `/metrics/hosts`; the process table's new columns; *Linux host*; the Sources window's hosts and Compose file; the development profile; E2E with signed datagrams. |

## Testing

- Pure: a frame read and refused; a signature checked in constant time over the
  bytes as received; a body refused for one bad sample; freshness by time and by
  sequence, including reordering inside the window; restarts from instance and
  boot, and an older instance ignored.
- Against a store: migration 4 takes agents' data and keeps a connection's; a
  process table in parts; a host description kept and read back; the watch
  seeded from the store.
- Browser: the hosts table, the Compose file, a ready-made layout from signed
  datagrams, a host that keeps restarting.
