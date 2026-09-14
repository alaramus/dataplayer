# The application agent

An agent that works on a person's data through the connections they added: what
it may do, how it asks, how an answer runs and is shown, and which models it
uses. Read this before adding a tool, before sending a connection's data to a
model provider, and before changing the chat window.

Decisions here: D133, D134, D135, D136, D137, D138, D139, D140, D141.

**Implementation status:** agreed on 2026-09-14. AI1 — the third-party transfer
flag —, AI2 — a new file by name — and AI3 are implemented; validation of the
chat window and AI4–AI6 are pending.

## What exists today

A connection carries `allow_third_party_transfer`, off by default and off for
every connection that existed before it (`c4f82b6e1d39`). It is set when the
connection is created or changed by its owner only; a grantee receives it in
the connection and is refused a change with 403. The connection window shows it
as a switch on its permissions page, disabled for a grantee. Nothing reads it
yet: the agent that will is AI4.

The file source has `create_file`, **New file** in the catalog menu: a name and
an empty file, the first capability added for the agent's sake and offered to
people as well (D133). What goes into the file is written by in-place editing
(D48).

The agent answers without tools in one floating chat window. A person stores a
key per provider and chooses a model from
`app/ai/models.json`; a message starts a run, whose Thinking step, reasoning and
answer stream on the `ai.runs` topic and are written to the transcript when the
answer ends. Stop keeps what was written, an answer is stopped after
`AI_RUN_TIMEOUT_SECONDS`, and a restart marks a working answer `interrupted`.
The first line of the first message is a conversation's title until the chosen
model writes one, unless the person renamed it.

```
backend/app/ai/
├── models.json      the curated models, validated at startup and in CI
├── catalog.py       reading that file
├── models.py        keys, choices and the transcript, and the API models
├── content.py       the one place conversation text is sealed and opened
├── preferences.py   keys set, removed and checked; the chosen model
├── conversations.py the transcript's rows and what the API sends of them
├── runner.py        an answer: recorded, streamed, settled, titled
├── checkpoints.py   LangGraph's saver: encrypted, strict, kept to its latest state
├── prompts.py       the system prompt and the title prompt
├── providers/       one module per provider SDK, and what its errors mean
├── topic.py         `ai.runs`
└── routes.py        /ai
backend/app/adapters/postgres/checkpoint_pool.py   the saver's psycopg pool
backend/app/prepare_checkpoints.py                 LangGraph's tables, at prestart
```

```
frontend/src/features/ai/
├── AiWindow.vue        the two columns, history and settings
├── AiConversation.vue  transcript, steps, Stop, copy and listen
├── AiSettings.vue      provider keys, model and confirmations
├── ChatMarkdown.vue    the D50 renderer in streaming mode
├── api.ts              vue-query ownership of server state
├── streaming.ts        open-fence protection and speech text
└── state.ts            the window and selected-chat restoration
```

```
GET    /api/v1/ai/models
GET    /api/v1/ai/settings
PATCH  /api/v1/ai/settings
PUT    /api/v1/ai/keys/{provider}
DELETE /api/v1/ai/keys/{provider}
POST   /api/v1/ai/keys/{provider}/check
GET    /api/v1/ai/conversations
POST   /api/v1/ai/conversations
DELETE /api/v1/ai/conversations
GET    /api/v1/ai/conversations/{conversation_id}
PATCH  /api/v1/ai/conversations/{conversation_id}
DELETE /api/v1/ai/conversations/{conversation_id}
POST   /api/v1/ai/conversations/{conversation_id}/messages
GET    /api/v1/ai/runs/{run_id}
POST   /api/v1/ai/runs/{run_id}/cancel
```

Two traps found while building it, both in LangGraph's PostgreSQL saver:

- **`setup()` builds its indexes `CONCURRENTLY`**, which waits for every open
  transaction in the database. Inside the application or a test process, which
  holds one, it waits for ever. It runs in `app.prepare_checkpoints`, from
  prestart and from CI after Alembic, and nowhere else.
- **`aprune` is declared and not implemented**: 3.1.2 raises
  `NotImplementedError`. `checkpoints.keep_latest` deletes the older states
  over LangGraph's own tables; a test that a conversation keeps one state, and
  one that it still continues, notice when an upgrade changes them.

The legacy application's `ai_handler` and `ChatAI` were read as evidence; what
is ported and what is not is listed in the spec.

## D133. The agent is one more client of the application

Tools run as the person who owns the conversation; no tool argument names a
user, a home or a path root. Every call goes through the connection access
funnel at the level the equivalent route requires (D33). What the interface
cannot do the agent cannot do: a missing capability is added to the source with
its command, and the agent reaches it through the registry. The agent works only
with connections the person added and never creates or saves one. The last
active workspace panel — connection, node, panel kind, never content — travels
with each message as a removable chip, so "here" means something.

Rejected: a built-in personal folder without a connection; every route
addresses a connection by id.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D134. Tools are a small general set over what sources already describe

`list_connections`, `browse_catalog`, `describe_node`, `read_rows`,
`run_query`, `list_actions`, `run_action`, `open_in_workspace`, `ask_user`.
Actions come from the registry with their parameter schema and are validated by
the action's own model, so a new source type or action needs no agent code. A
tool calls the service layer in process, not the HTTP API. A name is not an
identity: several matches become a question, never a guess. Results are bounded
and failures are the route's safe sentence (D2c). `open_in_workspace` is a
closed set of intents checked on the server; asked to open, the agent opens.

Rejected: a hand-written tool per operation found by vector search, and an MCP
process between the agent and the backend.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D135. Sending data to a third party is a connection policy its owner sets

A connection's third-party transfer flag is off by default, including for
existing connections, and only the owner changes it. It is general, not an agent
flag. It is checked before every tool call; every tool, changes included, is
refused on a connection that does not allow transfer, which the agent still sees
by name and type with a marker. The owner may Allow from the refused step.
Tool results are stored with their connection, and results of a connection that
no longer allows transfer are withheld from later context. There is no
user-level flag.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D136. Reading is free; a change asks, and the answer can last

Every change asks, with Allow once, Allow all changes in this chat (stored on
the conversation) and Allow all changes in every chat (a revocable setting).
Nothing is decided in the browser, and no permission exceeds the owner's policy:
a `read_only` connection (D66) is never written. An unasked change is still a
visible step. SQL reads follow D62; SQL changes run after confirmation as one
committed transaction, never an open one, with D46's preview for a drop and DDL.

Known deviation, accepted: under "every chat", data the agent reads can ask it to
change something and nobody is asked.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D137. An answer is a run the server owns, and its steps are visible

A run is a row before it is a task (D81), with closed states including
`awaiting_answer`; a step is written before it is announced, and Stop is a
command. A pause outlives a restart: answering it afterwards continues the run
from the model's saved state. A run that was working when the process stopped
is `interrupted`, and nothing is replayed. Limits: 50 tool calls, 15
minutes, one active run per conversation. The server words each step from a
tool template; substeps come from real progress; model time is a Thinking step
with the provider's reasoning as expandable text. A minimised window shows the
run in Working (D95) and a question in Needs you (D113). Tokens and duration are
recorded per step.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D138. The answer is Markdown, rendered as it arrives

The D50 renderer draws the answer in a streaming mode: settled blocks are
final, an open fence waits until it closes, re-rendering is throttled. Remote
resources stay blocked with no unblock, because injected data could turn an
image address into a leak. Relative links do nothing. At most 20 rows appear in
an answer, then the agent offers to open them. Copy gives raw Markdown; Listen
uses the browser's speech synthesis on plain text.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D139. The loop is LangChain v1 middleware inside one package

`create_agent` with summarisation, human-in-the-loop and limit middleware.
LangChain types stay in one backend package behind this project's run, step and
message models, held by an import contract; each provider integration has its
own module. The server decides per call whether a person is needed. Long
conversations are summarised. Tracing is a setting, off by default. Tests use a
scripted fake model; real-provider tests skip without a key.

Two stores with two roles: LangGraph's `AsyncPostgresSaver` holds the model's
working state, and this project's encrypted tables hold the transcript a person
reads, so an unreadable checkpoint after an upgrade loses no history. The saver
is used as shipped: its pool is built in `adapters/postgres/` by the lifespan,
`setup()` runs at prestart and `env.py` excludes its tables, its serializer
encrypts under `AI_CONTENT_KEY` with a test that no plaintext reaches its
columns, deserialization is strict, `durability="exit"` with older checkpoints
pruned, and versions are pinned and upgraded deliberately.

Rejected: an own loop, Deep Agents as the harness, Pydantic AI, a checkpointer
of this project's own, no checkpointer, the transcript only in the checkpointer.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D140. Models are a curated file; keys belong to the person

OpenAI, Anthropic, DeepSeek and Gemini. Models are a closed JSON list in the
repository — context window, maximum output, reasoning, image input — changed
with a release, validated at startup and in CI, served to the client through the
API. A stored model missing from the file reads as none chosen. One key per
provider per person, encrypted under `CONNECTOR_SECRET_KEY` and never returned,
with Check. The model is
chosen in the agent settings only. Each provider's reasoning must be carried
back inside a tool loop, and a test per provider proves it.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D141. One chat window holds the conversations and the agent's settings

One floating window, opened by the first button at the right of the application
header. Left column: New chat, history, Settings; settings replace the
conversation on the right. Keys, Model and Confirmations live here, not on
`/preferences`. Titles are written by the chosen model and renamable. A conversation is
kept until deleted, one at a time or all at once, and its content is encrypted
at rest under `AI_CONTENT_KEY`. No editing, tags, rewind, branches or search; attachments
later.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)
