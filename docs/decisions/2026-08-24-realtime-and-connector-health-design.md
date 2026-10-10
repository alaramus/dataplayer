# The socket, connection availability and the disabled connector

Date: 2026-08-24
Status: agreed
Subproject: 7a

## Goal

Build the real-time transport and its first consumer.

The transport is not needed for its own sake: bringing up a service under
Docker will sit on it (progress is a stream, not one answer), as will the
agent's output and loading rows into the grid. But a transport without a
consumer cannot be checked, so connection availability is built together with
it — it is small, it has a clear "done or not", and it honestly loads the
socket with everything that will be asked of it: subscription, sending at the
server's own initiative, disconnection, reconnection.

It also closes a thing that cannot be separated from availability: **the
disabled connector**. Disabled is not deleted — it stays in the list, it can
be read and enabled again, but it cannot be used and does not need checking.
Without this the monitor's rule reads as "poll everyone", and "everyone" is not
a rule.

## Premises

**Every source has `check_connection`.** It is declared in the base
`DataAdapter` contract, not in an optional capability. So the question "what
if the source cannot be checked" does not arise here, and 501 does not appear
in this subproject — unlike the catalog, fetch and actions.

**`ConnectionCheckResult` is already safe.** It reduces a driver exception to
an error kind and a message, because the exception text regularly contains the
connection string together with the password. The socket frame carries this
same object, not one of its own.

**The check deliberately does not take from the pool.** The manual check
already does this, and the reasoning is written right in `_adapter_for`: a
check must check the credentials, and a pooled connection will report "works"
even after the password has stopped matching. This came out while writing the
code and overturned the first wording of the premise — it said the opposite,
that polling is cheap because it takes a ready connection. The cost of polling
is one connection per source per round, and it is held down by the interval,
a concurrency ceiling and a backoff after a failure.

**The reasoning written in `connectorChecks.ts` is overturned by this
subproject.** It says why check state is not asked of the server: "otherwise
on screen load we will open a connection to every source". We decided to do
exactly that — while the screen is being looked at. The comment is rewritten
together with the code; it cannot be left contradicting it.

## Decisions

### R1 (D18). The transport knows no topic

`app/realtime/` is only the envelope, the topic registry and the socket hub.
Not a single import of `app.connectors`.

One route, `/api/v1/ws`. Messages are discriminated unions with
`extra="forbid"`, like `CatalogNode`:

```python
# client -> server
class WsAuth(BaseModel):      type: Literal["auth"];        token: str
class WsSubscribe(BaseModel): type: Literal["subscribe"];   topic: str
class WsUnsubscribe(BaseModel): type: Literal["unsubscribe"]; topic: str

# server -> client
class WsReady(BaseModel): type: Literal["ready"]; protocol: int
class WsEvent(BaseModel): type: Literal["event"]; topic: str; payload: ...
class WsError(BaseModel): type: Literal["error"]; code: ...; message: str
```

A topic is a `runtime_checkable` Protocol with two handles: a subscriber came,
a subscriber left. The registry holds factories; the objects are built by
`lifespan` and put into application state — whatever outlives a request
belongs to the application (D10), like the pool.

Rejected: a route for every need (`/ws/connector-health`, `/ws/agent`,
`/ws/docker`): the browser would then have several sockets, each with its own
authentication and its own reconnection, and the common code would have to be
pulled out into a shared place anyway — only later and from three copies.

Also rejected: "the socket carries the same requests as HTTP", as done in the
old application. There it is justified: the client is someone else's program,
and the socket saves it a handshake on every call. Here the client is our own,
HTTP requests are made by vue-query, and a second way to call the same routes
would be a second API with the same rights — that is, a second surface that has
to be protected equally.

### R2. The token arrives as the first frame

A browser cannot set a header on the WebSocket handshake. What remains is the
query string or the first message.

The query string is rejected: it writes the JWT into every access log, into
the browser history and into the `Referer` header. The socket opens
unauthenticated, gives nothing before `auth`, and closes if `auth` has not
arrived within the allotted seconds.

### R3 (D19). One monitor per user, and it lives while someone is looking

The subscription is "I watch my connections", with no enumeration. The monitor
is created when the user gets a first subscriber, and goes out with a short
delay after the last one leaves — otherwise a page reload kills it and
immediately builds it again.

The loop: reread the user's list of connectors (it may have changed), poll the
enabled ones with a concurrency limit and a timeout on each, put the result
into the monitor's memory and send it to all of this user's sockets.

A new subscriber first of all receives a snapshot of the last known state. So
a second tab is coloured at once and adds not a single call to someone else's
server — that is why the monitor is shared, not per socket.

A failed source gets a backoff: its interval doubles up to a ceiling and is
reset on success. Without it every loop runs into the connection timeout of a
dead host, and the live ones are checked less often than it.

The manual check (`POST /{id}/check`) puts its result into the monitor.
Otherwise there are two sources of truth on screen: the button said "ok", the
dot shows "down".

### R4 (D20). A disabled connector is not a source

`Connector.enabled: bool = True`, a migration, a field in `ConnectorPublic` and
in `ConnectorUpdate`.

The prohibition sits in `_adapter_for` — the only place where a stored
connector turns into a live adapter. The catalog, fetch, actions and the manual
check go through it, so the rule is written once and cannot be forgotten in a
new route. `_get_or_404` is not touched: a disabled connection can still be
read, renamed and enabled again.

The response code is 409. Not 404: the connector exists, and the client knows
about it. Not 403: it is the user's own, and rights are not the issue.

The monitor does not include disabled ones in its round, and the route that
disables one tells the monitor to forget the last result — otherwise a
connector enabled again glows yesterday's green for a second.

Rejected: a separate route `/{id}/disable`: this is one field of the
connector, and it is edited where the others are.

### R5. The dot is made up from two sources

There are four tones: `disabled` (yellow) overrides everything, then `unknown`
(grey), `ok`, `failed`.

`enabled` arrives with the list of connectors in vue-query — it is server
state. The last check result lives in Pinia — the server does not store it.
The split follows D6, and it also answers why "disabled" is not sent over the
socket: one fact in two places drifts apart.

There is no "checking" state. Polling is periodic, and blinking on every round
is noise, not information. The age of the last check is given in the tooltip.

### R6. The socket client is our own, not a library

`shared/realtime/socket.ts`: open, authenticate, resubscribe, reconnect with a
growing backoff and jitter. The "after opening do this" logic is ours anyway,
and without it what remains of `reconnecting-websocket` is the backoff alone.

Our own is checked with a fake `WebSocket` in Vitest — no server, no waiting on
time. Someone else's cannot be checked that way.

In the end there is no separate `useTopic.ts`: there is one subscriber —
`features/connectors/health.ts` — and a "subscription for the lifetime of a
component" wrapper would be a layer over one line. It will appear with the
second consumer.

### R7. Place in the layers

`app.realtime` stands between `app.adapters` and `app.users`:

```
api → system → connectors → adapters → realtime → users → core
```

The transport needs only users (authentication) and core. The availability
topic lives in `app/connectors/health.py` — it is about connectors — and
registers itself. Extension is a new module plus registration, not an edit to
the transport.

## How it is checked

Envelope and transport:

- an unknown `type` and an extra key are rejected;
- a socket without `auth` is closed when the time runs out; with an invalid
  token — at once;
- a subscription to an unregistered topic gives `error`, not a disconnect;
- no frame carries connector options or the password — a regression test, as
  for error text.

Monitor:

- a subscription gives a snapshot at once, then updates arrive;
- a second socket of the same user adds no polling;
- the backoff after a failure grows up to the ceiling and resets on success —
  a pure function, checked without a socket;
- a disabled connector does not get into the round.

Disabling:

- catalog, fetch, action and check on a disabled one give 409;
- reading, renaming and enabling again work;
- `mypy --strict`, `ruff`, `lint-imports` are clean, and `realtime` does not
  import `connectors`.

Client:

- reconnects and resubscribes by itself (Vitest, fake `WebSocket`);
- the dot turns green by itself, without clicks (Playwright);
- a disabled one glows yellow and does not open (Playwright).

**The first socket test is broken on purpose.** A socket and a shared event
loop are a place where it is easy to get a green test that simply waited for
nothing. A check that has never gone red means nothing.

## What has to be added to the tooling

`httpx` with `ASGITransport` cannot do WebSocket, and Starlette's `TestClient`
is synchronous and starts its own event loop — exactly the pool-and-loop trap
recorded in AGENTS.md. `httpx-ws` with its ASGI transport is added to the dev
dependencies, and the socket tests live in the same session loop as the rest.

The socket is opened **inside the test, not by a fixture**: the transport holds
an anyio scope, and a session fixture is closed in a different task from the
one it was opened in, which this scope does not allow. Helpers are in
`tests/utils/socket.py`.

A connection break arrives wrapped in an `ExceptionGroup`, so
`pytest.raises(WebSocketDisconnect)` does not catch it; there is a context
manager of its own for "the server hung up".

## Known deviations

**The monitor lives in the process.** With several workers each will have its
own, polling will be multiplied by their number, and a socket will receive only
what its own process checked. Today there is one process. The honest solution
is a shared channel (Redis pub/sub); it is recorded here rather than postponed
silently.

## What this subproject does not include

- long tasks with an "accepted / running / done" state — Docker needs them,
  and they have no consumer yet;
- check history and availability charts;
- notifications of a failure while the screen is closed;
- access rights: only the owner sees and does disabling, because other people's
  connectors do not exist yet;
- an availability check of a form draft — it already exists and stays manual.
