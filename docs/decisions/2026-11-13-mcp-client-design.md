# The agent calls outside MCP servers

2026-11-13. D360, D361.

## What was asked

The application agent works on a person's data through DataPlayer's own
tools (D134). A person who also uses an outside MCP server — an issue tracker,
a wiki, a search service, one of their own — wants the agent to call its tools
in the same chat. D357 made DataPlayer an MCP server; this is the other
direction.

## D360. An outside MCP server is a person's, reached over HTTP from the backend

- **A person's own.** The agent's settings, in the AI space, keep a list per
  person: a
  name, an address, an optional bearer token and other headers, a switch, and
  the tools switched off. Nobody else sees it and nothing is shared: an MCP
  server stands for a service account of whoever entered its token, so sharing
  it would hand that account to others. An administrator's list for everybody
  is left for when somebody needs it.
- **Streamable HTTP only.** The backend is the client, by MCP's Streamable HTTP
  transport. Stdio is refused: it means starting a program the person names
  inside the backend's container. The older SSE transport is not offered; the
  servers that matter speak Streamable HTTP, and a second transport is a second
  set of failures to explain.
- **Secrets are sealed** as a provider key is, under `CONNECTOR_SECRET_KEY`,
  and never come back: the list says that a token is set and which headers
  exist, not their values.
- **The address is checked before every connection.** An address must be http
  or https, and every address its host resolves to must be public. A private,
  loopback, link-local or reserved one — `localhost`, `10.x`, a container
  name such as `db` — is refused unless `MCP_CLIENT_ALLOW_PRIVATE` is set for
  the installation, because the backend sits inside the network of the
  database, the metrics store and the containers it starts, and a person's
  address must not be a way to reach them. The SDK follows a redirect only
  within the address's own origin.
- **The SDK stays in one module**, `app/ai/mcp_client.py`, beside the server's
  `app/ai/mcp_server.py`, by the rule that keeps a driver in its adapter.

Rejected: stdio (above); a server shared like a connection (above); trusting
the address once when it is saved (a name can resolve elsewhere later).

Known deviation: the name is resolved for the check and again by the HTTP
client, so a host that answers differently between the two can still lead
inside. Closing that needs a transport that connects to the checked address,
left for when the setting is used on an exposed installation.

## D361. Its tools join the agent's in a chat, named by server, and a change asks

- **Listed when a run starts.** The tools of every server switched on, and on in
  this chat, are read with `tools/list`, kept in the process for five minutes
  and offered beside DataPlayer's own as `‹server›__‹tool›`, cut to the 64
  characters providers accept. A server that does not answer in time is left
  out of that answer; the rest of the chat goes on.
- **One connection per call.** Each call opens a session, initializes, calls the
  tool and closes. A run can pause for days on a question (D137) and resume in
  another process; a session held open across that would be a session lost.
- **Reading is free, anything else asks.** A tool whose annotations say
  `readOnlyHint` is a read. Every other tool is a change and goes through
  D136's gate: a read-only chat refuses it, ask shows the card with the tool's
  arguments as its preview, allow and Jev decide as they do for a statement.
  The hint is the server's word, trusted because the person chose the server.
- **What comes back is data.** Text parts are joined, other parts named and
  left out, the whole bounded to D134's 64 KiB, and the tool's description
  tells the model that what the server returns is not an instruction. A failure
  is one of three sentences — unreachable, refused the credentials, failed —
  never the transport's text.
- **On or off in a chat.** The composer lists the servers switched on in the
  agent's settings, each on by default; turning one off is kept on the conversation.
- **The chat's agent only.** Quick chat has no tools (D158), and `/mcp` does not
  pass another server's tools on (D357).

Known deviation, accepted: data the agent read from a connection that allows
third-party transfer (D135) can be passed to an outside tool as its argument.
The flag already says that the data may leave the server; the card shows the
arguments before a tool that is not a read runs, unless the person allowed
every change.

Rejected: a session held for a run (above); `langchain-mcp-adapters` (a second
client of the same SDK, around the step, bound and gate of D134 and D136 rather
than through them); every outside tool treated as a change (a search tool would
then ask on every call).

## Slices

One: the spec, the server table and its routes, the address check, the client,
the tools in a run, the conversation's switch, the section in the agent's
settings, the composer's menu, the guide, tests.
