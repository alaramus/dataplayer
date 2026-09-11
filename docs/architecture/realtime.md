# Realtime

The one socket, what may be said on it, and the first thing that says anything.
Read this before adding something the server has to tell the client without
being asked.

Decisions here: D18, D19.

## What exists today

One route, `/api/v1/ws`. A socket opens unauthenticated, presents a token as
its first frame, and is closed if it does not. After that it may subscribe to
topics by name, and it receives whatever those topics push until it goes away.

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

The frames are written out twice — Pydantic models on one side, a TypeScript
union on the other — because OpenAPI 3.1 has no WebSocket channel, so
`frontend/src/client` cannot carry them. The two are held together by the
end-to-end scenarios in `frontend/tests/health.spec.ts`, which are the only
place both sides meet. This is a known deviation from "the generated client is
the only description of the API", and the honest fix is to publish the socket
schema in the OpenAPI document under `x-websocket`, as the old application did.

## D18. The transport does not know a single topic

`app/realtime/` carries frames and nothing else. It has no import of
`app.connectors`, and the import contract holds it there: `app.realtime` sits
between `app.adapters` and `app.users`, so a topic can reach the transport and
never the other way round.

A topic is a `runtime_checkable` Protocol with two hands — a subscriber
arrived, a subscriber left — and a registry of factories. The objects are built
by the application lifespan and closed by it, for the same reason as the
connection pool: a topic that keeps a background task alive is exactly the
thing that outlives a request (D10).

Rejected: a route for each need (`/ws/connector-health`, `/ws/agent`). The
browser would then hold several sockets, each with its own authentication and
its own reconnect, and the common part would still have to be extracted —
later, and out of three copies.

Rejected too: carrying the same requests the HTTP routes take, as the old
application's public socket does. That is right there, where the client is a
foreign program saving a handshake per call. Here the client is ours and makes
its requests through vue-query, so a second way to invoke the same routes would
be a second surface with the same rights to defend.

The token arrives as the first frame because a browser cannot set a header on
the WebSocket handshake, and a token in the query string is written into every
access log, into browser history, and into the Referer of anything the page
loads next.

Spec: [The socket, health and a switched-off connector](../decisions/2026-08-24-realtime-and-connector-health-design.md)

## D19. A monitor belongs to a user, and lives only while somebody watches

Subscribing to `connector.health` means "watch my connections", without naming
them. The first subscriber of a user starts a monitor; the last one to leave
stops it, after a short grace so that reloading a page does not tear it down
and build it again from knowing nothing.

Per user and not per socket: two tabs of one person would otherwise double the
traffic to somebody else's database for the sake of the same coloured dot. A
second socket is handed the last known state at once and costs nothing.

A round reads the user's switched-on connections, probes those that are due
with a bounded number at a time, and announces each result as it lands. A
failure doubles that connection's interval up to a cap: a dead host answers by
timing out, so probing it as often as a live one makes every round as slow as
its worst member.

A probe does not borrow from the pool. This matches what the manual check
already does and it is deliberate — a check is meant to exercise the
credentials, and a pooled connection would go on reporting a source as up after
its password stopped working.

The manual check announces its result through the same topic, so pressing the
button and the dot beside the connection cannot end up saying different things.

**Known deviation.** The monitor lives in the process. With several workers
each would have its own, the probing would be multiplied by their number, and a
socket would only ever hear what its own process found out. Today there is one
process. The honest fix is a shared channel — Redis pub/sub — and it is written
down here rather than left to be discovered.

Spec: [The socket, health and a switched-off connector](../decisions/2026-08-24-realtime-and-connector-health-design.md)

## A trap on the client side

**A subscription is released with the scope that made it.** `useConnectorHealth`
and `useAccessRequestEvents` returned a `stop` that no caller ever called, and
the workspace page is mounted twice while the server check settles — so the
first listener stayed behind and every event was handled twice. It went
unnoticed for as long as Quasar drew the notifications, because Notify groups
two identical messages into one with a counter on it; the first thing that drew
them itself (D114) showed two cards. Both composables now dispose with their
scope, and a unit test stops a scope and expects the listener to go.

## A trap in the end-to-end scenarios

Playwright's thirty-second default is the budget for the whole test, not for
one assertion. A scenario that waits for a probe waits up to a full interval,
twice over, and runs out of budget while the dot on screen is perfectly
correct — the failure names the assertion, so it reads as a bug in the code.
`health.spec.ts` sets its own budget and says why.

## What the client does

One socket for the application, opened lazily: nothing connects until a screen
asks to watch something, and it closes when the last watcher goes. It is ours
rather than a library's because the part that matters — authenticate on open,
then restate every subscription — is ours either way; what a library would have
added is the reconnect delay, which is six lines and is spread, so that tabs
which dropped together do not come back together.

What the dot shows is made of two facts from two places, and deliberately so
(D6): whether a connection is switched off is a field of the connector and
arrives with the list through vue-query; what the last probe said is pushed and
lives in Pinia. `connectorState.ts` puts them together in one place, because
the dot needs the tone and the icon around it needs the words — and the dot
cannot carry its own tooltip, being drawn over the icon with pointer events
off.
