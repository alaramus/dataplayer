# DataPlayer as an MCP server

2026-11-13. D357, D358.

## What was asked

A third-party agent — Claude Code, Cursor, Codex, a script — connects to
DataPlayer and does work on a person's data: finds a table, reads it, runs a
query, runs an action. The application agent (D133–D136) already does this
from inside the chat; the question is how another agent does it from outside.

## D357. The agent's tools, offered over MCP by the backend itself

- **One process.** The server is a route of the backend, `/mcp`, speaking MCP's
  Streamable HTTP transport, stateless, answering in JSON. It is not a second
  server: D124 keeps the backend one process, and the application agent's
  design already rejected an MCP process between an agent and the backend for
  the shared admin secret and the cache of user tokens it needs.
- **The same tools, through the same code.** `list_connections`, `search`,
  `browse_catalog`, `describe_node`, `read_rows`, `run_query`, `list_actions`
  and `run_action` are defined once in `app/ai/tools.py` over a host that each
  caller supplies: the chat's run, which records steps and asks with cards, or
  the MCP request, which does neither. A bound, a limit or a check added to a
  tool reaches both. `open_in_workspace` and `ask_user` stay in the chat:
  an outside agent has no workspace on screen and asks its own person itself.
- **The same checks.** Every call goes through the connection access funnel as
  the person the token belongs to, and the third-party transfer flag (D135)
  is checked before every call exactly as for the application agent: an
  outside agent is a third party by definition. A connection whose owner did
  not allow transfer is seen by name and type with `transfer_not_allowed` and
  nothing else of it; there is no Allow from the refusal, because there is no
  person on the other end of the call to ask.
- **The `mcp` SDK stays in one module**, `app/ai/mcp_server.py`, by the rule
  that keeps a driver in its adapter.

Rejected: a separate MCP process (above); offering the HTTP API itself as the
tools (two hundred routes, none of them shaped for a model, and the bounds of
D134 lost); a flag of its own for MCP beside D135's (two switches for one
question — may this connection's data leave the server — that a person would
have to keep in step). An earlier draft let issuing a token stand for consent
to transfer; it was withdrawn, because the flag is the connection owner's and
a grantee issuing a token would otherwise send out data the owner kept in.

## D358. A personal access token, read-only or full

- **The person makes it** in Preferences → MCP access: a name, an optional
  expiry and a policy. It is shown once, at creation, and never again; the
  server keeps its SHA-256 and the first characters for recognising it in the
  list. It is deleted to be revoked. Its last use is recorded.
- **It is the person.** A token carries no rights of its own: what its owner
  may see and change today is what it may, and an owner who is deactivated
  takes every token with them.
- **Two policies.** `read_only` refuses every change — a statement that
  changes data, an action above reading — with a sentence and before
  anything runs. `full` runs a change without asking: there is no card on the
  other end, and the person who made the token chose to trust whatever holds
  it. Nothing in between: a change waiting on the Needs-you sheet for a call
  that has already timed out at the client was considered and left out.
- **The token is a bearer token** in `Authorization`. A missing, unknown,
  expired or revoked one is answered 401 with `WWW-Authenticate: Bearer`.
- **OAuth later.** MCP's authorization flow, which lets a client such as
  claude.ai sign in through a browser, is a second way to the same `/mcp` and
  comes as a decision of its own.

Rejected: handing out the session's JWT (it expires with the session, cannot
be revoked alone, and is the configuration the application agent's design
already rejected); a token limited to chosen connections (the transfer flag
already keeps out what may not leave; left for when somebody needs it).

## Slices

One: the spec, the token table and its routes, the shared tools, `/mcp`,
the Preferences section, tests, a client configuration in the guide.
