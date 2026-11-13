# DataPlayer as an MCP server

How an agent outside DataPlayer works on a person's data: the `/mcp` route,
the tokens it is entered with, and what it may do. Read this before adding a
tool to the agent, changing a token, or changing what `/mcp` answers. The
tools themselves, their bounds and the transfer flag are in [ai.md](ai.md).

Decisions here: D357, D358.

## What exists today

```
backend/app/ai/
├── tools.py          the tools, once, over a host the caller supplies
├── mcp_tokens.py     the token table, making, listing, deleting, verifying
├── mcp_routes.py     /ai/mcp-tokens: the person's tokens
└── mcp_server.py     /mcp: the token check, the MCP server, its host
frontend/src/features/preferences/McpSection.vue   Preferences → MCP access
```

A client is configured with the server's address and a token, for example in
Claude Code:

```bash
claude mcp add --transport http dataplayer https://dataplayer.example/mcp \
  --header "Authorization: Bearer dp_mcp_…"
```

## D357. The agent's tools, offered over MCP by the backend itself

`/mcp` is a route of the backend, MCP's Streamable HTTP transport, stateless
and answering in JSON, so it lives in the one process of D124 and needs no
second server. Its tools are the application agent's — `list_connections`,
`search`, `browse_catalog`, `describe_node`, `read_rows`, `run_query`,
`list_actions`, `run_action` — defined once in `app/ai/tools.py` over a
`ToolHost` the caller supplies: the chat's run records steps and asks with
cards, an MCP request does neither. `open_in_workspace` and `ask_user` are
the chat's only. The bounds of D134 hold.

Every call goes through the access funnel as the token's owner, and the
third-party transfer flag is checked before every call as D135 states: a
connection that does not allow transfer is seen by name and type with
`transfer_not_allowed`, with no Allow from the refusal, since nobody is on the
other end of the call to ask. `search` looks only inside the connections the
call names. The `mcp` SDK is imported by `app/ai/mcp_server.py` alone.

Rejected: a separate MCP process, the HTTP API offered as tools, and a
transfer flag of MCP's own beside D135's.

Spec: [DataPlayer as an MCP server](../decisions/2026-11-13-mcp-server-design.md)

## D358. A personal access token, read-only or full

A person makes a token in Preferences → MCP access with a name, an optional
expiry and a policy. It is shown once; the server keeps its SHA-256 and its
first characters, records its last use, and deletes it to revoke it. The
token has no rights of its own: it acts as its owner does today, and a
deactivated owner takes it along.

`read_only` refuses a change — a changing statement, an action above reading
— with a sentence before anything runs; `full` runs it without asking. A
missing, unknown or expired token is answered 401 with
`WWW-Authenticate: Bearer`. MCP's OAuth flow is a later, second way in.

Rejected: the session's JWT as the token, and a token limited to chosen
connections.

Spec: [DataPlayer as an MCP server](../decisions/2026-11-13-mcp-server-design.md)
