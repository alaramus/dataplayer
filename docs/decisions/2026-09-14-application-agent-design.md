# The application agent

Date: 2026-09-14. Decisions: D133 through D141, in [ai](../architecture/ai.md).

Status: agreed in discussion with the user on 2026-09-14. AI1, AI2, AI3, AI4,
AI5 and AI6 implemented. AI3b validation is pending. Slices below.

## Outcome

A person opens the agent from `AI` beside `Data` and `Dashboards` in the space
switch. The AI space holds New chat, the conversation history and the agent's
settings on the left, and the conversation on the right. They are separate
cards divided by the ordinary draggable workspace separator; the remembered,
collapsible left card cannot occupy more than 40% of the space. AI covers the
data workspace by the same contract as Dashboards: data panels remain mounted
and detached panels remain visible.

The person writes in their own words — "show me the tables in my connection
'test'", "create a folder with a file example.txt in my files connection",
"open orders", "how many rows here are from September" — and the agent does it
with the connections that person added, with that person's rights, and answers
in Markdown. Reading happens at once; every change asks first unless the person
allowed it. Above each answer a collapsed line says what the agent is doing now,
step by step, so long work never looks like an endless spinner.

This is an agent of this application, working on the user's data through
connections. It is not a general coding agent. The legacy application grew
towards a Claude Code of its own; that direction is not continued.

## Evidence

Legacy sources read as workflow evidence:

- `dbwebtool/webdb/ai_handler/` — `handlers/dispatcher.py`,
  `handlers/actions.py`, `handlers/command.py`, `handlers/connector.py`,
  `pipeline/langgraph_mcp.py`, `pipeline/graph.py`, `pipeline/state.py`,
  `pipeline/tool_executor.py`, `pipeline/context_curation.py`,
  `pipeline/stream_sse.py`, `pipeline/subagent_runners.py`, `mcp/bridge.py`,
  `mcp/server_registry.py`, `mcp/tool_loader.py`, `mcp/dispatcher.py`,
  `skills/loader.py`, `providers/models.py`, `providers/helpers.py`,
  `storage/models.py`, `config/settings.py`, `config/models_info.py`.
- `dbwebtool/webdb/server/MCP/dataplayer_mcp_server.py` and
  `dbwebtool/configs/tools/` — 22 `TOOL.md` definitions and `_endpoints.yaml`.
- `myquasar/src/myapp/components/ChatAI/` — `ChatAi.vue`,
  `composables/useChatStreaming.ts`, `composables/useTextToSpeech.ts`,
  `core/chatTypes.ts`, `core/settings.ts`, `BrowserLLM/`.
- `allow_third_party` in `dbwebtool/webdb/common_option_adapter.py` and
  `core/login_models.py`, and its consent dialogs in `myquasar`:
  `ThirdPartyConsentDialog.vue`, `ConnectorThirdPartyConsentDialog.vue`,
  `EditConnectorModal.vue`.
- The LangChain and Deep Agents documentation as published on 2026-09-14.

What the legacy code showed:

- LangGraph is used as a three-node loop (context → agent → tools) and a
  checkpointer. Summarisation of older turns, long-term memory, skills, a plan
  with steps, sub-agents and confirmations are written by hand beside it — the
  things LangChain v1 middleware and Deep Agents now provide. The chat model
  class is chosen by a substring of the model name, and `ChatDeepSeekThinking`
  subclasses `ChatOpenAI` only to round-trip `reasoning_content`.
- A run lives in process dictionaries (`active_operations`, `active_tasks`,
  `_thread_tools`, per-thread locks) and in the SSE response. Closing the tab
  while a confirmation is pending loses the run.
- Tools are found by semantic search in Qdrant, registered on a separate MCP
  server process per chat session (at most 30, the oldest evicted), and
  executed by that process calling DataPlayer's HTTP API with the user's session
  token and a shared admin secret.
- `ai_terminal` runs a shell command and `execute_python` runs
  `sys.executable` on the server host, confined only by the working directory.
  External Claude Code and Codex sub-agents need `docker exec`, `docker build`,
  npm at runtime and per-user volumes.
- `mcp_connect_handler` returns the user's raw session token inside a
  ready-made MCP client configuration.
- "Allow for this session" and "auto-confirm all" are decided in the browser,
  the latter in `localStorage`; the server accepts `confirmed` from the client.
- There are two consent flags, both off by default: `allow_third_party` in user
  options and in connector options. The connector flag is switched on from a
  consent dialog by whoever meets it, not only by the connection's owner.
- History, media, tags, include flags, checkpoint anchors and branches live in
  separate tables; rewinding truncates history and checkpoints in step.
- `MAX_ITERATIONS` is 1000; the default history limit is 10¹¹.
- Listening to a message uses the browser's `speechSynthesis`, in chunks, after
  stripping Markdown.

What the current application showed:

- Every data route addresses a connection by id; a name is a label and two
  connections of one owner may share it ([backend](../architecture/backend.md)).
- The file source has `create_folder`, `upload`, `rename`, `delete`, `paste`,
  `create_archive`, `extract_archive` and in-place editing of an existing file
  (D48). Nothing creates a text file with given content.
- `/preferences` stores closed-set values in plaintext. Connector credentials
  and query content are encrypted under purposes of `core/crypto.py`.
- The D50 renderer renders a complete document; progressive rendering is out of
  scope there.
- The application header has an `actions` slot before the fullscreen and theme
  toggles, and the workspace page leaves it empty.
- `psycopg` may be imported only by `adapters/postgres/` (`backend/.importlinter`).

## What is ported and what is not

Ported as behaviour, rewritten as code:

- A chat with streamed answers, a conversation history, an automatic title,
  copying a message and listening to it.
- Tools that read and change the user's data through connections, with
  confirmation of changes.
- Summarising older turns when a conversation outgrows the model's context.
- The third-party transfer consent, as a connection policy.
- A curated list of models and their capabilities in a JSON file.
- Showing the model's reasoning.

Not ported:

- Editing a sent message, tags and search by tags, the per-message "do not send
  to the model" flag, rewind, branches, search over history.
- Export and import of chats; import of Claude Code, Codex or opencode sessions
  from disk.
- Image and speech generation, voice input, the in-browser model.
- Shell, Python and file-workspace tools on the server host; external CLI
  sub-agents in containers (D86).
- Qdrant tool search, `TOOL.md` definitions, the endpoint registry and the
  separate MCP server process.
- Spec and plan artifacts, sub-agents, long-term memory, skills.
- The `%%` prefix in the terminal. DataPlayer has no terminal.
- A user-level third-party flag (D135).
- An MCP client configuration that hands out a session token.

Wanted and left for later: attachments in a message; trying self-hosted
Langfuse and LangSmith for tracing.

Not discussed, and not part of this design: AI helpers inside the query editor
and charts, DataPlayer as an MCP server for external clients, external MCP
servers, local models.

## D133. The agent is one more client of the application

The agent does what the person could do in the interface, with the person's
rights and through the same checks.

- **Tools run as the person who owns the conversation.** The server takes the
  user from the run. No tool argument names a user, a home directory or a path
  root, so a row in somebody's table saying "create a file in the folder of
  user 42" has nothing to aim at.
- **Every tool call goes through the connection access funnel** with the level
  the equivalent route requires (D33). A standing below it is answered with the
  refusal sentence the route would give.
- **What the interface cannot do, the agent cannot do.** When a request needs a
  missing capability, the capability is added to the source, with its command
  in the interface, and the agent reaches it through the registry. The first
  instance is a file source action that makes a file by name (AI2); what goes
  into it is written through in-place editing (D48), which the interface
  already has.
- **The agent works with the connections the person added**, owned and
  granted, and with nothing else. "My folder" is a file connection. With none,
  the agent says so and offers to open the new-connection form; the person
  fills it in and saves it. The agent never creates or saves a connection, so a
  password never passes through a model.
- **The screen is context only when explicitly attached.** Opening the chat
  attaches nothing, and moving between tabs does not change the message. A plus
  beside the composer lists every open workspace tab, including a tab detached
  into a floating window; the person may select up to five. Connection id, node
  id and panel kind travel as removable chips, never content. The selection is
  cleared after a successful send and retained after a failed send, so the same
  tabs are not sent with a later question by accident. "Here" and "this table"
  resolve to the attached set. Access and D135 apply to each reference.

Rejected: a built-in personal folder available without a connection. Every
route addresses a connection by id, so it meant either a second addressing
scheme through every route, cache key and saved tab, or an automatic,
undeletable connection per user with its own rules for grants, renaming and
existing root connections. The user chose to work only with added connections.

## D134. Tools are a small general set over what sources already describe

The legacy agent had one hand-written tool per operation and needed a vector
search to find them. DataPlayer's sources describe themselves (D13) and their
actions are objects with a parameter model, a level and `destructive` (D9), so
the tools are general and few:

| Tool | What it does |
| --- | --- |
| `list_connections` | id, name, type, access level, and D135's marker |
| `browse_catalog(connection, node?)` | the nodes of one level |
| `describe_node(connection, node)` | what a node is, a relation's model (D75, D22) |
| `read_rows(connection, node, …)` | a bounded page (D2c's closed predicates) |
| `run_query(connection, sql)` | D136 |
| `list_actions(connection, nodes)` | the registry's answer, with each action's parameter JSON Schema |
| `run_action(connection, action, nodes, params)` | validated by the action's own model, as a form is |
| `open_in_workspace(target)` | a closed set of intents |
| `ask_user(question, choices)` | a card with choices in the chat |

Rules:

- A new source type or a new action reaches the agent with no agent code.
- A tool is a direct call into the service layer of the backend process. It is
  not HTTP back into the API and not a call through a second process.
- **A name is not an identity.** The agent resolves names through
  `list_connections` and the catalog; more than one match is an `ask_user` with
  the candidates, never a guess.
- A result is compact and bounded. A failure is the safe sentence the route
  would give; driver text never reaches the model (D2c).
- `open_in_workspace` opens a connection's catalog, a node's preferred panel, a
  query result or a file. The server checks access before announcing the
  intent; the client opens an ordinary panel, which reads with its own checks.
  When the person asks to open something, it opens at once; when they ask to
  see or show it, the answer stays in the chat.

Rejected: one tool per operation described by hand. Twenty-two `TOOL.md` files
covered a fraction of the operations, needed an endpoint registry beside the
routes and a Qdrant search so the model could find them. Rejected: an MCP
server process between the agent and the backend — a second server, a shared
admin secret and a cache of user tokens for calls the backend makes itself.

## D135. Sending data to a third party is a connection policy its owner sets

- A connection carries a third-party transfer flag, **off by default** and off
  for every existing connection after its migration.
- **Only the owner changes it**, the rule `tab_color` and D66's execution policy
  follow. A grantee sees the flag and cannot change it; otherwise the person
  holding a grant would decide that the owner's data may leave.
- **It is not an agent flag.** Anything that sends a connection's data outside
  the installation checks it.
- **It is checked before every tool call** on a connection, not once per run,
  because the owner may switch it off in the middle of one.
- Every tool is refused on a connection that does not allow transfer, changes
  included: an action's result reaches the model too.
- The agent still sees such a connection's name and type, marked "transfer not
  allowed", so it can say why it did not do what was asked.
- The refused step offers the owner **Allow**, which switches the flag on after
  an explicit confirmation and lets the run continue. A grantee reads "Ask the
  owner to allow it".
- **What was sent is not sent again.** Every tool result is stored with the
  connection it came from. When context is built for the model, the results of
  connections that no longer allow transfer are replaced with
  "[removed: connection no longer allows third-party transfer]". Nothing can
  recall what already reached a provider.
- **There is no user-level flag.** A person who enters their own provider key
  has consented to sending their messages there; whether data may go is the
  connection's question.

Every provider in D140 is external, so this flag governs every read the agent
makes.

## D136. Reading is free; a change asks, and the answer can last

- Reading needs no confirmation.
- Every change asks: an action, a file change, DML, DDL. The card offers **Allow
  once**, **Allow all changes in this chat** and **Allow all changes in every
  chat**.
- "This chat" is stored on the conversation on the server. "Every chat" is a
  setting of the person, visible and revocable in the agent settings. Nothing
  is decided in the browser.
- **A person's permission never exceeds the owner's policy.** A connection whose
  owner set `read_only` (D66) is not written by the agent under any permission.
- A change nobody was asked about is still a visible step: what was done, where,
  and how many rows it affected.
- **SQL reads go through D62**: a read-only transaction, the statement timeout,
  a bounded result snapshot (D64).
- **SQL changes run after confirmation as one run in one transaction**, committed
  at its end. The agent never holds an open transaction between steps. A drop
  and every DDL statement show D46's preview — the statement rehearsed and
  rolled back — in the confirmation card.

Accepted risk, stated to the user: under "every chat", data the agent reads — a
row, a file — can ask it to change something, and nobody is asked. Visible steps
and Stop are the defence; nothing undoes a completed change.

Rejected: a permission scoped to one tool on one connection. Safer, but it asks
more often; the user chose all changes in the chat.

## D137. An answer is a run the server owns, and its steps are visible

- **An answer is a run: a row before it is a task** (D81). The request that
  sends a message records the run and returns.
- The states are closed: `running → awaiting_answer → running → succeeded |
  failed | cancelled | interrupted`. `awaiting_answer` covers a confirmation and
  an `ask_user`.
- **A step is written before it is announced** on the socket. The socket is a
  courtesy and the row the authority, so a reload restores the step line where
  it was.
- **A pause outlives a restart.** A run awaiting an answer keeps
  `awaiting_answer`: its pause is in the model's working state (D139), and
  answering after the restart continues the run from the pause without calling
  the model again for what was already done. A run that was working when the
  process stopped is marked `interrupted`; nothing is replayed.
- **Stop is a separate command.** The current step is marked cancelled; what was
  completed stays listed.
- **Limits per run:** 50 tool calls, 15 minutes, one active run per
  conversation. Reaching a limit stops the run with a sentence naming the limit
  and the step it stopped at.
- **The server words a step, from a template per tool and its arguments** —
  "Running query on "test"" — never the model, so a step says what was actually
  called.
- A step with real progress has substeps from the operation itself, such as the
  statement ordinal and rows received (D64). No percentages.
- **Model time is a step**: "Thinking · 25 s", with the reasoning the provider
  returned as expandable text inside it. DeepSeek returns its reasoning in full;
  Anthropic, Gemini and OpenAI return a summary when asked, or nothing. The step
  is shown either way.
- Tool calls made together are concurrent steps.
- While running, the collapsed line shows the current step and its elapsed
  time; afterwards it reads "N steps · T".
- While the chat window is minimised, a running answer appears in Working (D95)
  and a pending confirmation or question in Needs you (D113).
- Tokens and duration are recorded per step and per run, so that prompts, tools
  and models can be compared later.

Rejected: the streamed HTTP response as the run, as in the legacy application.

## D138. The answer is Markdown, rendered as it arrives

- **The answer is Markdown, rendered by the D50 renderer**: emphasis, tables,
  code, KaTeX, `mermaid`, `echarts`, `svg` and the callout cards. A deletion
  answers "deleted" or "not deleted" in words, not with a component.
- **Streaming mode.** Settled paragraphs and closed fences render for good; an
  open fence shows a placeholder until it closes; re-rendering is throttled. A
  half-received `echarts` option never reaches ECharts.
- **Remote resources stay blocked, with no way to unblock them in the chat.**
  Data the agent reads can make the model write an image address that carries
  that data; loading the image would send it out without a click.
- Relative links do nothing in the chat, which has no source node to resolve
  them against. Opening goes through `open_in_workspace`.
- The system prompt names the fences and ECharts series the bundle draws, and
  changes together with the renderer.
- **At most 20 rows appear in an answer.** Beyond that the agent says how many
  there are and offers to open them.
- **Copy** puts the raw Markdown on the clipboard. **Listen** reads plain text
  through the browser's speech synthesis, without code, charts, diagrams or
  reasoning; nothing is sent to a provider.

Rejected: DataPlayer components — the grid, a chart — inside a message, with
data coming from the server rather than the model. The user chose the model's
Markdown answer.

## D139. The loop is LangChain v1 middleware inside one package

- The agent loop is LangChain v1 `create_agent` with middleware: summarisation,
  human-in-the-loop, call limits.
- **LangChain and LangGraph types stay inside one backend package.** The rest of
  the application sees this project's run, step, question and message models.
  An import-linter contract holds that, as it holds `psycopg`; each provider
  integration — `langchain-openai`, `langchain-anthropic`,
  `langchain-google-genai`, `langchain-deepseek` — sits in a module of its own.
- Whether a call needs a person is decided by the server per call (D135, D136),
  not by a static list of tool names.
- **A long conversation is summarised, not truncated**, so the connection and
  table discussed at its start are not forgotten.
- **Two stores with two roles.** LangGraph's own PostgreSQL checkpointer
  (`AsyncPostgresSaver`) is the model's working state: the messages exactly as
  providers returned them, the summary, a pause. The transcript a person reads
  — messages, the final Markdown, steps, reasoning — is this project's
  encrypted tables. A conversation only grows, so neither is kept in step with
  the other; legacy's anchors and truncation for rewind are not needed. If an
  upgrade leaves the working state unreadable, the transcript stays and the
  conversation continues from it, without the detail of earlier tool results.
- **The checkpointer is used as shipped, with these conditions:**
  - its connection pool and the saver are built in `adapters/postgres/`, the
    package allowed `psycopg`, by the application lifespan (D10), with the
    connection settings LangGraph requires (`autocommit`, `dict_row`,
    `prepare_threshold=0`); the agent package receives the saver and is added
    to the driver contract;
  - `setup()` runs at prestart; `env.py` excludes its tables so Alembic does not
    read them as tables to drop;
  - its serializer encrypts under `AI_CONTENT_KEY`, and a test writes a marker
    string into a conversation and finds it in no column of LangGraph's tables,
    because plain values of state are stored outside the serializer;
  - deserialization is strict (`LANGGRAPH_STRICT_MSGPACK` or an explicit list
    of modules): by default it rebuilds any Python type, which is code execution
    for whoever can write to the table;
  - `durability="exit"`: state is written when an answer ends or pauses, not
    after every step, and older checkpoints of a conversation are pruned, since
    nothing goes back to them;
  - LangChain and LangGraph versions are pinned, upgraded in a commit of their
    own after reading the changelog, and a test continues a conversation saved
    before the upgrade.
- **Tracing is a setting, off by default**, so that self-hosted Langfuse and
  LangSmith can be tried later through LangChain's standard callbacks.
  LangSmith sends traces, data included, to a cloud; it is tried on test data.
- Tests run the loop against a scripted fake chat model. A test against a real
  provider needs a key and is skipped without one, through the registry in
  `tests/utils/services.py`.

Rejected: a loop of this project's own. The legacy code shows summarisation,
confirmations and limits are thousands of lines, and they are what the
middleware provides. Rejected: a checkpointer of this project's own over its
session and Alembic tables — it keeps every rule without an exception, but its
interface would have to follow LangGraph's changes by hand, and LangChain
changes often. Rejected: no checkpointer — confirmations and the summary would
be written again beside the middleware, and a pause would not survive a
restart. Rejected: the transcript only in the checkpointer — a change of its
format would erase what a person keeps until they delete it. Rejected: Deep Agents as the harness. Its filesystem, todo
list and sub-agents are the tools of a coding agent; the role its filesystem
plays for a large result is played here by a D64 result snapshot. Rejected:
Pydantic AI — stricter types and a smaller ecosystem; the user chose LangChain.

## D140. Models are a curated file; keys belong to the person

- Providers: **OpenAI, Anthropic, DeepSeek, Gemini.**
- **The models are a closed list in a JSON file in the repository**: provider,
  model id, display name, context window, maximum output, reasoning, image
  input. It changes with a release. There is no editor in the application and no
  path to override it.
- The file is validated by a strict model when the server starts and by a test
  in CI. An unknown field, an unknown provider or a duplicate id fails both.
- The client receives the list through the API; there is no second copy in the
  frontend. It offers only models of providers the person has a key for.
- A stored choice no longer in the file reads as no model chosen, and the
  settings ask for one — the way a stored check interval nobody recognises
  reads as the default.
- **A person stores one key per provider**, encrypted at rest under
  `CONNECTOR_SECRET_KEY` — a credential like a connection's — and never
  returned. The settings know "set" or "not set" and offer Replace, Remove and
  Check. Check makes a small call that uses a tool, which also proves the model
  can call tools.
- The model is chosen in the agent settings, not per conversation.
- **The reasoning round-trip is a known trap.** Inside a tool loop each provider
  requires part of its previous answer back: DeepSeek `reasoning_content`,
  Anthropic signed thinking blocks, Gemini thought signatures, OpenAI encrypted
  reasoning items. Dropping it fails the next call with 400; legacy met it with
  DeepSeek. A loop test per provider proves it is carried.

Rejected, in the order the discussion went: a provider as a connection (it
would put models into the list of data sources); one key for the installation
from an administrator; switching the model inside a chat; the model list read
from each provider's API — chosen, then reversed, because only Gemini reports a
context window and OpenAI's list mixes embedding, speech and image models;
editing the file from the application with an override path on the server —
chosen, then reversed in favour of changing the list with a release.

## D141. One application space holds the conversations and the agent's settings

- **AI is the third application space**, selected beside Data and Dashboards at
  the foot of the screen. There is no duplicate button in the application
  header and no chat window.
- **Two separate cards.** The left one, collapsible, resizable and capped at 40%
  of the space, holds New chat, the conversation history by last activity, and
  Settings at its foot. The ordinary workspace separator moves it. Settings
  open in the right card in place of the conversation, and the list stays.
- **An empty history opens the composer.** Entering AI with no active agent
  conversations opens an unsaved local draft in the right card. It enters
  history only after its first message is sent.
- **Settings**: Keys (per provider), Model, and Confirmations with "Allow all
  changes in every chat". The agent's settings live here, not on `/preferences`.
- **A title is automatic and can be renamed.** The first line of the first
  message becomes the title at once; after the first answer a title written by
  the chosen model replaces it, unless the person renamed the conversation.
- **A conversation is kept until its owner deletes it.** Delete per
  conversation; Delete all, with a confirmation. Deletion is permanent. Deleting
  a conversation with a running answer cancels the run first. Deleting a user
  deletes their conversations.
- **Conversation content is encrypted at rest** — messages, reasoning and tool
  results — with a required key of its own, `AI_CONTENT_KEY`, and never written
  to logs, for the reason D63 gives for query content.
- A reload reopens the window on the same conversation, and a running answer
  goes on showing its steps.
- The window is a stable window (D132).
- Not in the window: editing a message, tags, rewind, branches, search.
  Attachments came later, with D142.

## D142. A message may carry the person's own files

Asked for on 2026-09-18: the plus of the composer attached only workspace tabs,
and people wanted to send a document or a photo of their own.

- **Text and images only, at first.** Text is anything that reads as UTF-8;
  an image is PNG, JPEG, WebP or GIF. PDF was offered and left out — DeepSeek
  does not read it, and the three providers that do each take it differently —
  and Office documents would need text extracted on the server.
- **Told by the bytes, not the name.** The server sniffs an image's signature
  and decodes text strictly; the type a browser reports is used only by the
  composer, to refuse early what the server would refuse anyway.
- **Part of the message.** A file is stored with its message in the same
  commit, sealed like the text, shown in the transcript — an image as itself,
  text by its name — and deleted with it. The model sees it in later turns too,
  because it is in the working state like the rest of the message. The other
  two options were keeping a copy in the person's folder as well, and sending a
  file once and keeping only its name.
- **Images only where they are read.** The models file already says which
  models take images (D140). The picker offers images only to those; an image
  attached before the model was changed marks itself and disables Send. The
  server refuses an image to any other model in the same words.
- **The plus is a menu.** "Workspace tabs…" and "Files from computer…". Drag
  and drop and pasting from the clipboard were offered and left for later.
- **One form, no uploads ahead.** Text, tabs and files are one multipart
  request, so a message and its files exist together or not at all; a separate
  upload route would have left files that were never sent. The tabs travel as
  one JSON field typed by a root model, because FastAPI reads a form field
  typed as a list by collecting every value of that name.
- **Bounded.** Five files, 5 MB an image (the strictest provider's limit), 256
  KB of text, 10 MB together. The settings API sends the numbers, so the
  composer never keeps its own copy.

## Slices

Each slice is implemented with its tests and verified with the checks
ENGINEERING.md names for the sides it touches.

### AI1 — third-party transfer

The flag of D135 on a connection: the column, a migration that sets it off for
every existing connection, owner-only change, the field in the public
connection, a checkbox in the connection window that a grantee sees disabled.

Acceptance: a new and an existing connection have the flag off; the owner
switches it on and off; a grantee's attempt is refused; the checkbox shows the
state and is disabled for a grantee.

### AI2 — a new file by name

A file source action, **New file**, that asks for a name and nothing else, as
an IDE does, and makes an empty file in the folder being looked at: a taken name
is refused as it is for upload, the name goes through D8's containment rule, and
the result names the branch to re-read. A command in the catalog offers it.

Corrected during implementation: the first version also took the file's
content in the same form. The user wanted the IDE's gesture — a name, then the
file — so content is written afterwards through in-place editing (D48).

Acceptance: an empty file is created; a taken name, `..`, an absolute path and
a drive-bearing name are refused; the catalog shows the new file.

### AI3 — the window, the settings and a chat without tools

The models file and its validation; per-provider keys with Check; the model
choice; the chat window and its button; conversations and runs (D137) with the
Thinking step and reasoning; streamed Markdown (D138); Stop; the 15-minute
limit; copy and listen; automatic title, rename, delete, delete all;
encryption of content; `interrupted` after a restart; the tracing setting. The
checkpointer under D139's conditions, with the transcript in this project's
tables.

Split during implementation into AI3a, the backend and its API, and AI3b, the
window. Corrected during AI3a:

- **LangGraph's `setup()` cannot run inside the application.** Its migrations
  build indexes `CONCURRENTLY`, which waits for every open transaction; the test
  process holds one, and the first run on an empty database hung. It runs in
  `app.prepare_checkpoints`, from prestart and from CI after Alembic, which is
  where D139 put it.
- **The saver's `aprune` is not implemented** (3.1.2 raises
  `NotImplementedError`), so pruning to the latest state is written against
  LangGraph's tables in `checkpoints.keep_latest`, and tests notice when an
  upgrade changes them.
- **The tracing setting is left for the trial of Langfuse and LangSmith**:
  LangSmith is switched on by its own environment variables, and Langfuse needs
  a callback that nothing here would exercise yet.

Acceptance: a broken models file fails a test and startup; a key is never
returned; a stored model missing from the file asks for a choice; an answer
streams and survives a reload; Stop cancels; a restart marks a running answer
interrupted; a marker string written into a conversation appears in no column
of the checkpointer's tables; deserialization refuses a type outside the
allowed list; `alembic check` reports nothing with the checkpointer's tables
present; an open `echarts` fence does not render until it closes; a remote
image is not loaded; copy and listen work; a renamed conversation keeps its
name after the first answer.

### AI4 — reading

The reading tools of D134, `open_in_workspace`, `ask_user`, the screen-context
chip, D135 before every call with the transfer-not-allowed marker, Allow for the
owner, withholding results of connections that stopped allowing transfer, the
20-row rule, the 50-tool-call limit, steps with substeps.

Acceptance: "show the tables in X" lists them; two connections named X produce
a question; "open orders" opens the panel; a grantee's agent cannot read a
connection whose flag is off and says why; switching the flag off removes that
connection's earlier results from the next context; the tool-call limit stops a
run with its sentence; the agent does not read a connection the person has no
grant for.

Corrected during AI4, each caught by its acceptance test:

- **A refused statement escaped the step.** `run_query` admits reads only, and
  its refusal (`queries.execution.RunRefused`) was not among the failures a
  tool step settles, so a refused run left its step open and ended the answer
  as a model failure. The step now ends failed with the source's own sentence
  as the tool's result.
- **The transfer policy withheld the refusal itself.** A
  `transfer_not_allowed` result names its connection, so withholding by
  connection id replaced it too, and the agent could not say why it stopped.
  Only results that carry a connection's data are withheld; a refusal always
  reaches the model.
- **A named conversation paid for a title it discarded.** The title was written
  by the model and then refused by the storage rule; a conversation whose owner
  named it now never spends the call.

### AI5 — changes

`run_action` and SQL changes under D136: the confirmation card with its three
answers, D46's preview for a drop and DDL, the owner's `read_only` policy above
every permission, Needs you while the window is minimised, a visible step for
every change.

Acceptance: a change asks; a pending confirmation answered after the backend
restarts continues the run; "this chat" stops asking in that conversation only;
"every chat" stops asking everywhere and is revocable; a `read_only` connection
is never written; a drop shows its preview; a failed statement commits nothing.

### AI6 — long conversations

Summarisation of older turns when a conversation approaches the model's context
window, from D140's file. It may move earlier if conversations reach the limit
before AI5.

Acceptance: a conversation longer than the context window goes on answering
with facts from its start.

Settled during AI6: the trigger is an absolute token count computed from the
window in D140's file (`AI_SUMMARY_TRIGGER_FRACTION` of it, 0.8 by default),
not LangChain's fractional trigger, because that one asks the provider's
profile for the window and neither the scripted model nor every real one knows
it. The newest `AI_SUMMARY_KEEP_MESSAGES` (20 by default) stay verbatim; the
same model and key write the summary, and the transcript a person reads is
never rewritten.

### AI7 — files in a message

D142: the plus as a menu, the picker, the chips, the form, the table of files,
the route that serves one, the model's image and text blocks.

Acceptance: a text file and an image reach the model and stay in the
transcript; somebody else's file is not found; an image is refused to a model
that does not read it, before and after sending; a file that is neither text
nor an image, a sixth file and an empty message are refused before a run
exists.

## Open points for implementation

Settled on 2026-09-14 and folded into D137, D139, D140 and D141: where the
model's state is stored, which keys encrypt provider keys and conversations, and
which model writes a title.

Settled during AI4: a tool result is at most 64 KiB and 20 rows, and names
truncation explicitly. Step templates are `Listing connections`, `Browsing
catalog in …`, `Describing …`, `Reading rows from …`, `Running query on …`,
`Opening …`, and `Waiting for your answer`, with `Running action "…" on …`
added in AI5. Every ordinary open workspace panel
whose identity can be represented by `ScreenContext` may be attached explicitly;
opening the AI space attaches none automatically.

## Validation

AI1, on 2026-09-14: the full backend suite (2933 passed, 119 skipped for
servers not started), `mypy app`, `ruff check app tests`, `lint-imports`,
`alembic check`, frontend `type-check`, `lint`, `test:unit`, the Playwright
scenarios `connectors.spec.ts` and `sharing.spec.ts`, and `check-docs.sh`, all
clean.

AI2, on 2026-09-14, after the correction: `tests/adapters/test_file_actions.py`,
`tests/connectors/test_action_routes.py` and `tests/adapters/test_routes.py`
(133 passed), `mypy app`, `ruff check app tests`, `lint-imports`, frontend
`type-check` and `lint`, the Playwright scenarios `files.spec.ts` and
`actions.spec.ts`, and `check-docs.sh`, all clean. The name check and the
exclusive creation were each broken once to see their tests fail. A trap found
on the way: on Windows, creating a file over a folder of the same name raises
`PermissionError` rather than `FileExistsError`.

AI3a, on 2026-09-14: the full backend suite (2991 passed, 119 skipped for servers
not started), of which `tests/ai` is 42, `mypy app`, `ruff check app tests`,
`lint-imports` (eight contracts, two of them new), `alembic check`, the backend
image started with prestart preparing LangGraph's tables, and `check-docs.sh`.
Broken once each to see the check fail: encryption of the checkpointer, strict
deserialization, pruning to the latest state, and LangChain imported outside
the agent package.

AI4, on 2026-09-16: the full backend suite (3014 passed, 119 skipped for
servers not started), of which `tests/ai` is 65 — the reading acceptances end
to end through the API with the scripted model over a real connection — `mypy
app`, `ruff check app tests`, `lint-imports`, frontend `type-check`, `lint` and
`test:unit` (1721 passed), and `check-docs.sh`, all clean. Each correction
above was first seen red, then green.

AI5, on 2026-09-16: the full backend suite (3022 passed, 119 skipped for
servers not started), of which `tests/ai` is 73 — the change acceptances end to
end: the card asks with its three answers and its rehearsal preview, once
stores nothing, this chat is stored on the conversation and covers only it,
every chat is stored on the person and revocable from settings, a pending
confirmation survives the startup sweep and continues the run, a failed
statement commits nothing, a read grant is refused in D66's sentence, and a
destructive action previews and drops — `mypy app`, `ruff check app tests`,
`lint-imports`, frontend `type-check`, `lint` and `test:unit` (1724 passed),
and `check-docs.sh`, all clean.

AI6, on 2026-09-16: the full backend suite (3024 passed, 119 skipped for
servers not started), of which `tests/ai` is 75 — a conversation past the
window is summarised and answers with facts from its start, the summary is
what the next answer starts from, the transcript a person reads is untouched,
and a short conversation is never summarised — `mypy app`, `ruff check app
tests`, `lint-imports`, and `check-docs.sh`, all clean. No frontend changed.
The acceptance was first seen red without the middleware, then green.
