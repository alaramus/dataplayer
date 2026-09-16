# The application agent

An agent that works on a person's data through the connections they added: what
it may do, how it asks, how an answer runs and is shown, and which models it
uses. Read this before adding a tool, before sending a connection's data to a
model provider, and before changing the chat window.

Decisions here: D133, D134, D135, D136, D137, D138, D139, D140, D141.

**Implementation status:** agreed on 2026-09-14. AI1 — the third-party transfer
flag —, AI2 — a new file by name —, AI3, AI4, AI5 and AI6 are implemented;
validation of the chat window is pending.

## What exists today

A connection carries `allow_third_party_transfer`, off by default and off for
every connection that existed before it (`c4f82b6e1d39`). It is set when the
connection is created or changed by its owner only; a grantee receives it in
the connection and is refused a change with 403. The connection window shows it
as a switch on its permissions page, disabled for a grantee. The agent's tools
check it before every call (D135).

The file source has `create_file`, **New file** in the catalog menu: a name and
an empty file, the first capability added for the agent's sake and offered to
people as well (D133). What goes into the file is written by in-place editing
(D48).

The agent answers in the AI application space, reading through the tools of
D134: `list_connections`, `browse_catalog`, `describe_node`, `read_rows`,
`run_query`, `list_actions`, `run_action`, `open_in_workspace` and `ask_user`.
Every tool call goes through the connection access funnel as the person who
owns the conversation, and the transfer flag is checked before every call: a
connection that does not allow transfer answers with a `transfer_not_allowed`
marker, the owner is offered Allow from that step, and a grantee is told to ask
the owner. Results of a connection whose flag was switched off are withheld
from later context — a refusal itself never is, since it carries no data and
the agent needs it to say why it stopped. Results are bounded to 64 KiB and 20
rows, and a run stops after 50 tool calls with its own sentence.

A change asks first (D136): a `run_query` whose script changes data and a
`run_action` above reading pause the run on a confirmation card with Allow
once, Allow all changes in this chat and Allow all changes in every chat, the
second stored on the conversation, the third on the person's settings and
revocable there. The card carries a preview — a drop and every DDL statement
rehearsed in a rolled-back transaction, an action's own preview where it has
one. A `read_only` connection is refused before anybody is asked, in D66's
sentence, and so is a level the person does not hold. Confirmed SQL runs as one
transaction that commits only when every statement succeeded, and a visible
step records it, one substep per statement. A paused run keeps its question
across a restart, and while it waits the conversation is flagged `waiting`,
which the Needs-you sheet lists with a button that opens that chat. A person
stores a
key per provider and chooses a model from
`app/ai/models.json`; a message starts a run, whose Thinking step, reasoning and
answer stream on the `ai.runs` topic and are written to the transcript when the
answer ends. Tool steps are named by the server (`Browsing catalog in …`,
`Reading rows from …`), with a query's statements as substeps. A conversation
that nears the chosen model's context window — `AI_SUMMARY_TRIGGER_FRACTION` of
the window from `app/ai/models.json` — is summarised by the same model before
the next answer: older turns become a summary in the working state while the
newest messages stay verbatim (`AI_SUMMARY_KEEP_MESSAGES`), and the transcript
a person reads is never rewritten. Stop keeps what
was written, an answer is stopped after
`AI_RUN_TIMEOUT_SECONDS`, and a restart marks a working answer `interrupted`.
The first line of the first message is a conversation's title until the chosen
model writes one, unless the person renamed it — a named conversation never
spends a model call on a title.

The model selector groups models by provider. Every model row shows whether
that provider's one key is configured; its key button opens the same provider
key window, so setting an Anthropic key, for example, enables every Anthropic
model rather than attaching a secret to one model.

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
├── tools.py         the tools, the transfer policy, the change gate and the call limit
├── providers/       one module per provider SDK, and what its errors mean
├── topic.py         `ai.runs`
└── routes.py        /ai
backend/app/adapters/postgres/checkpoint_pool.py   the saver's psycopg pool
backend/app/prepare_checkpoints.py                 LangGraph's tables, at prestart
```

```
frontend/src/features/ai/
├── AiSpace.vue         the two columns, history and settings
├── AiConversation.vue  transcript, steps, the confirmation card, Stop, copy, listen and the context chips
├── AiContextDialog.vue the open tabs a message may carry
├── AiSettings.vue      provider keys, model and confirmations
├── ChatMarkdown.vue    the D50 renderer in streaming mode
├── attention.ts        a waiting conversation as a Needs-you item (D113)
├── api.ts              vue-query ownership of server state
├── context.ts          which open panels a chip may name, and the open intent
├── streaming.ts        open-fence protection and speech text
└── state.ts            selected-chat restoration and a chat requested from outside; the shared space store remembers AI
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
POST   /api/v1/ai/runs/{run_id}/answer
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
with connections the person added and never creates or saves one. Opening the
chat attaches nothing. A plus beside the composer lists the open workspace
tabs, including tabs detached into floating windows; the person may attach up
to five. Their connection, node and panel kind travel with the next message as
removable chips, never their content. A successful send clears the selection
so it cannot be sent twice by accident; a failed send keeps it. Switching tabs
never changes the selection.

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
to 64 KiB and 20 rows, with an explicit truncation marker, and failures are the
route's safe sentence (D2c). `open_in_workspace` is a
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
no longer allows transfer are withheld from later context; a refusal names the
connection but carries nothing of it, so it is never withheld — it is how the
agent says why it stopped. There is no
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
tool template (`Listing connections`, `Browsing catalog in …`, `Describing …`,
`Reading rows from …`, `Running query on …`, `Running action "…" on …`,
`Opening …`, and
`Waiting for your answer`); substeps come from real progress; model time is a Thinking step
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
conversations are summarised: the trigger is a fraction of the model's window
from D140's file as an absolute token count, because no provider profile can be
trusted to know it, and the summary is written by the same model and key the
conversation uses. Tracing is a setting, off by default. Tests use a
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

## D141. One application space holds the conversations and the agent's settings

AI is the third application space beside Data and Dashboards, reached from the
status-bar space switch. Data panels remain mounted,
and detached panels remain visible, by the same covering contract as
Dashboards. Left column: New chat, history, Settings; settings replace the
conversation on the right. The two cards have the ordinary draggable workspace
separator; the left card is remembered, collapsible and capped at 40% of the
space. Keys, Model and Confirmations live here, not on
`/preferences`. Titles are written by the chosen model and renamable. A conversation is
kept until deleted, one at a time or all at once, and its content is encrypted
at rest under `AI_CONTENT_KEY`. No editing, tags, rewind, branches or search.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)
