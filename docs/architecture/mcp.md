# MCP: DataPlayer as a server, and the servers its agent calls

How an agent outside DataPlayer works on a person's data: the `/mcp` route,
the tokens it is entered with, and what it may do. Read this before adding a
tool to the agent, changing a token, or changing what `/mcp` answers. The
tools themselves, their bounds and the transfer flag are in [ai.md](ai.md).

Decisions here: D357, D358, D360, D361.

## What exists today

```
backend/app/ai/
├── tools.py          the tools, once, over a host the caller supplies
├── mcp_tokens.py     the token table, making, listing, deleting, verifying
├── mcp_routes.py     /ai/mcp-tokens: the person's tokens
└── mcp_server.py     /mcp: the token check, the MCP server, its host
frontend/src/features/preferences/McpSection.vue   Preferences → MCP access
```

A client is configured with the server's address and a token. The window that
shows a new token gives the line or the file entry for Claude Code, Codex,
Gemini CLI, Kimi Code CLI, Cursor, VS Code and opencode
(`features/preferences/mcp.ts`); in Claude Code, for example:

```bash
claude mcp add --transport http dataplayer https://dataplayer.example/mcp \
  --header "Authorization: Bearer dp_mcp_…"
```

## D357. The agent's tools, offered over MCP by the backend itself

`/mcp` is a route of the backend, MCP's Streamable HTTP transport, stateless
and answering in JSON, so it lives in the one process of D124 and needs no
second server. Its tools are the application agent's — `list_connections`,
`search`, `browse_catalog`, `describe_node`, `read_rows`, `run_query`,
`list_actions`, `run_action`, `read_guide` (D359) — defined once in `app/ai/tools.py` over a
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

## Outside MCP servers the agent calls

```
backend/app/ai/
├── mcp_servers.py        the server table, its sealed secrets, the address check
├── mcp_client.py         the SDK's client: listing tools, calling one
├── mcp_tools.py          the tools offered in a run, their listings kept a while
└── mcp_client_routes.py  /ai/mcp-servers
frontend/src/features/ai/McpServersSection.vue   the agent's settings, MCP servers
```

A person adds a server in the AI space's settings with a name, an address, an
optional bearer token and other headers; **Tools** asks the server what it
offers, and each tool can be switched off. The composer of a chat switches
servers on and off for that chat.

## D360. An outside MCP server is a person's, reached over HTTP from the backend

A server is its owner's alone and is not shared. The backend is the client by
Streamable HTTP; stdio and the older SSE transport are not offered. The token
and the headers are sealed under `CONNECTOR_SECRET_KEY` and never come back:
the list says a token is set and names the headers. Before every connection
the address must be http or https and every address its host resolves to
public; a private, loopback, link-local or reserved one is refused unless
`MCP_CLIENT_ALLOW_PRIVATE` is set. The SDK follows a redirect only within the
same origin. The `mcp` SDK is imported by `mcp_client.py` and `mcp_server.py`
alone.

Known deviation: the host is resolved for the check and again by the HTTP
client, so a name that answers differently between the two can still lead
inside.

Rejected: stdio, a server shared like a connection, and trusting an address
once when it is saved.

Spec: [The agent calls outside MCP servers](../decisions/2026-11-13-mcp-client-design.md)

## D361. Its tools join the agent's in a chat, named by server, and a change asks

When a run starts, the tools of each server that is on, and on in that chat,
are listed — kept in the process for five minutes — and offered as
`‹server›__‹tool›`, at most 64 characters. A server that does not answer is
left out of that answer. Each call opens its own session and closes it, so a
run paused for days resumes without one. A tool with `readOnlyHint` is a read;
any other goes through D136's gate with its arguments as the card's preview.
What comes back is bounded as D134's results are and described to the model as
data; a failure is unreachable, refused the credentials, or failed, never the
transport's text. Quick chat and `/mcp` do not offer these tools.

Known deviation, accepted: data read from a connection that allows transfer
(D135) can go to an outside tool as an argument; the card shows it unless every
change is allowed.

Rejected: a session held for a run, `langchain-mcp-adapters`, and every outside
tool treated as a change.

Spec: [The agent calls outside MCP servers](../decisions/2026-11-13-mcp-client-design.md)
