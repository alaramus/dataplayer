# Realtime

The one socket, what may be said on it, and the first thing that says anything.
Read this before adding something the server has to tell the client without
being asked.

Decisions here: D18, D19.

## What exists today

One route, `/api/v1/ws`. A socket opens unauthenticated, presents a token as its
first frame, and is closed if it does not. After that it may subscribe to topics
by name and receives whatever those topics push until it goes away.

```
backend/app/
├── realtime/
│   ├── messages.py      the frames, as discriminated unions
│   ├── topics.py        what a topic is, the registry, the topic set
│   └── routes.py        the socket, and one session per connection
└── connectors/
    └── health.py        the first topic: availability of a user's connections

frontend/src/
├── shared/realtime/
│   ├── socket.ts        connect, authenticate, resubscribe, reconnect
│   └── client.ts        the application's one socket
└── features/connectors/
    ├── health.ts        subscribing, and keeping the store in step
    └── connectorState.ts  what state a connection is in, in one place
```

More topics followed, each beside what it announces: `queries/topic.py` (D64),
`jobs/topic.py` (D81), `shares/topic.py` (D61), `metrics/live.py` (D127) and
`ai/topic.py` (D137).

Known deviation from "the generated client is the only description of the API":
the frames are written out twice, Pydantic models on one side and a TypeScript
union on the other, because OpenAPI 3.1 has no WebSocket channel and
`frontend/src/client` cannot carry them. The two are held together only by
`frontend/tests/health.spec.ts`, where both sides meet. The honest fix is to
publish the socket schema in the OpenAPI document under `x-websocket`.

## D18. The transport does not know a single topic

`app/realtime/` carries frames and nothing else. It has no import of
`app.connectors`, and the import contract holds it there: `app.realtime` sits
between `app.adapters` and `app.users`, so a topic can reach the transport and
never the other way round.

A topic is a `runtime_checkable` Protocol with two hands — a subscriber arrived,
a subscriber left — and a registry of factories. The objects are built by the
application lifespan and closed by it, for the same reason as the connection
pool: a topic that keeps a background task alive is exactly the thing that
outlives a request (D10).

The token arrives as the first frame because a browser cannot set a header on
the WebSocket handshake, and a token in the query string is written into every
access log, into browser history, and into the Referer of anything the page
loads next.

Rejected: a route for each need (`/ws/connector-health`, `/ws/agent`). The
browser would hold several sockets, each with its own authentication and
reconnect, and the common part would still have to be extracted — later, and out
of three copies. Rejected too: carrying the same requests the HTTP routes take.
The client here is ours and makes its requests through vue-query, so a second way
to invoke the same routes would be a second surface with the same rights to
defend.

A terminal is the one exception: each has a socket of its own, authenticated the
same way and never reconnected ([D148](terminals.md)).

Spec: [The socket, health and a switched-off connector](../decisions/2026-08-24-realtime-and-connector-health-design.md)

## D19. A monitor belongs to a user, and lives only while somebody watches

Subscribing to `connector.health` means "watch my connections", without naming
them. The first subscriber of a user starts a monitor; the last one to leave
stops it, after a short grace so that reloading a page does not tear it down and
build it again from knowing nothing.

Per user and not per socket: two tabs of one person would otherwise double the
traffic to somebody else's database for the sake of the same coloured dot. A
second socket is handed the last known state at once and costs nothing.

A round reads the user's switched-on connections, probes those that are due with
a bounded number at a time, and announces each result as it lands. A failure
doubles that connection's interval up to a cap: a dead host answers by timing
out, so probing it as often as a live one makes every round as slow as its worst
member.

How often a connection falls due is the user's own choice, read from their
preferences at the start of every round, so changing it takes effect under a
monitor already running. The choices are a closed set — a free interval is a
field somebody puts one second into, and that cost lands on the server being
probed. "Never" is one of them: nothing is probed, the monitor drops what it
knew, and the screen clears its dots rather than keep claiming something nobody
is checking. `HEALTH_INTERVAL_SECONDS` is how often the monitor comes round,
which is also the shortest choice offered and the tick a change of mind is
noticed on.

A probe does not borrow from the pool, matching the manual check: a check is
meant to exercise the credentials, and a pooled connection would go on reporting
a source as up after its password stopped working. The manual check announces
its result through the same topic, so the button and the dot beside the
connection cannot say different things.

Known deviation:

- **Every topic lives in the process** — the monitors and each topic's list of
  sockets — which is correct only because the backend runs as one process (D124).
  Under several, probing would be multiplied by their number, and a socket would
  hear only what its own process found out or was told: a manual check, a run, a
  job, an access request. The fix is a shared channel such as Redis pub/sub, and
  D104 asks for a measured need before Redis carries anything but the read cache.

Spec: [The socket, health and a switched-off connector](../decisions/2026-08-24-realtime-and-connector-health-design.md)

## Two traps

**A subscription is released with the scope that made it.** `useConnectorHealth`
and `useAccessRequestEvents` returned a `stop` no caller ever called, and the
workspace page is mounted twice while the server check settles — so the first
listener stayed behind and every event was handled twice. It went unnoticed while
Quasar drew the notifications, because Notify groups two identical messages into
one with a counter; the first thing that drew them itself (D114) showed two
cards. Both composables now dispose with their scope, and a unit test stops a
scope and expects the listener to go.

**Playwright's thirty-second default is the budget for the whole test**, not for
one assertion. A scenario that waits for a probe waits up to a full interval,
twice over, and runs out of budget while the dot on screen is correct — the
failure names the assertion, so it reads as a bug in the code. `health.spec.ts`
sets its own budget and says why.

## What the client does

One socket for the application, opened lazily: nothing connects until a screen
asks to watch something, and it closes when the last watcher goes. It is ours
rather than a library's because the part that matters — authenticate on open,
then restate every subscription — is ours either way; what a library would have
added is the reconnect delay, which is six lines and is spread, so that tabs
which dropped together do not come back together.

What the dot shows is made of two facts from two places, deliberately (D6):
whether a connection is switched off is a field of the connector and arrives with
the list through vue-query; what the last probe said is pushed and lives in
Pinia. `connectorState.ts` puts them together in one place, because the dot needs
the tone and the icon around it needs the words — and the dot cannot carry its
own tooltip, being drawn over the icon with pointer events off.
