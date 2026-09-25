# The application agent

An agent that works on a person's data through the connections they added: what
it may do, how it asks, how an answer runs and is shown, and which models it
uses. Read this before adding a tool, before sending a connection's data to a
model provider, and before changing the chat window.

Decisions here: D133, D134, D135, D136, D137, D138, D139, D140, D141, D142, D156, D157, D158, D159.

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
the agent needs it to say why it stopped. Results are bounded to 64 KiB, 20
rows and 100 nodes of a catalog level a call, read on from an offset, and a run
stops after 50 tool calls with its own sentence.

A change asks first (D136): a `run_query` whose script changes data and a
`run_action` above reading pause the run on a confirmation card with Allow
once, Allow all changes in this chat and Allow all changes in every chat, the
second stored on the conversation, the third on the person's settings and
revocable there. The chat's composer holds a policy choice
— read only, ask, allow, Jev — and offers the person's every-chat switch as a
separate choice, in the caution colour; a read-only chat answers the tool with a sentence
instead of pausing, whatever the person allowed in general. The card carries a preview — a drop and every DDL statement
rehearsed in a rolled-back transaction, an action's own preview where it has
one. A `read_only` connection is refused before anybody is asked, in D66's
sentence, and so is a level the person does not hold. Confirmed SQL runs as one
transaction that commits only when every statement succeeded, and a visible
step records it, one substep per statement. A paused run keeps its question
across a restart, and while it waits the conversation is flagged `waiting`,
which the Needs-you sheet lists with a button that opens that chat. A person
stores a key per provider and chooses a model from `app/ai/models.json` in the
chat it is for, the settings holding what a new chat starts with; a message
starts a run, whose Thinking step, reasoning and
answer stream on the `ai.runs` topic and are written to the transcript when the
answer ends. While a run is open, its elapsed time advances on the screen's
shared clock even when no new run event arrives; after it ends, the recorded
finish time fixes the duration. Tool steps are named by the server (`Browsing catalog in …`,
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
Each provider group also offers Jev model selection (D157) when the person's
provider and TypeSafe keys are set. A conversation remembers its previous model
as fallback. The actual model used is shown on the run.

The experimental Jev change policy (D156) is a fourth conversation policy.
Its choice is disabled until the person saves a verified TypeSafe key in AI
settings. Jev decides each proposed change independently; its denial or failure
prevents the change and appears on the tool step. It never grants connection
access or overrides a read-only connection.

```
backend/app/ai/
├── models.json      the curated models, validated at startup and in CI
├── catalog.py       reading that file
├── models.py        keys, choices and the transcript, and the API models
├── content.py       the one place conversation text is sealed and opened
├── attachments.py   files sent with a message: what is taken, what the model is given
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
├── AiSpace.vue         the two columns, history, projects and settings
├── AiChatRow.vue       one chat in the history: pin, project, archive
├── AiConversation.vue  transcript, steps, the confirmation card, Stop, copy, listen, the context chips and the composer's own model
├── AiContextDialog.vue the open tabs a message may carry
├── AiFileChip.vue      one file of a message, before and after it is sent
├── AiMessageFiles.vue  the files a sent message carried, read with the person's token
├── AiSettings.vue      provider keys, model, confirmations and the archive
├── ChatMarkdown.vue    the D50 renderer in streaming mode
├── attention.ts        a waiting conversation as a Needs-you item (D113)
├── api.ts              vue-query ownership of server state
├── attachments.ts      which picked files join a message, by the server's rules
├── context.ts          which open panels a chip may name, and the open intent
├── dictation.ts        the browser's recogniser behind the composer's microphone
├── outline.ts          the questions of a conversation, and which one is being read
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
GET    /api/v1/ai/projects
POST   /api/v1/ai/projects
PATCH  /api/v1/ai/projects/{project_id}
DELETE /api/v1/ai/projects/{project_id}
GET    /api/v1/ai/conversations
POST   /api/v1/ai/conversations
DELETE /api/v1/ai/conversations/archived
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
tabs that name a connection or node the tools can act on — catalogs, rows,
content, structure, summaries, records, charts and relationships — including
tabs detached into floating windows; the person may attach up
to five. The query library, consoles and captured results are not listed:
their content never travels and no tool reads it, so listing them would
invite the model to claim it saw them. A file from the computer is the other
thing the plus offers, and its content does travel (D142). Their connection, node and panel kind travel with the next message as
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
What it opens while another space is shown floats over that space in a window
of its own (D93) instead of calling Data forward, so the chat stays in front;
a tab already open in a column is lifted into the window, and docking it from
Data puts it back where it was. Only a panel that cannot float opens in
Data.

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

A conversation carries one of three policies, chosen in its own composer: read
only, ask, or allow. Ask is where every conversation starts, and it asks with
Allow once, Allow all changes in this chat (which sets the conversation to
allow) and Allow all changes in every chat (a revocable setting). Read only is
the narrow end: the change is refused before anybody is asked, and it stands
above what the person allowed in general, because the narrower rule wins.
The composer also offers "every chat" itself: it is the settings' switch, not a
fourth policy, so choosing it in a read-only chat sets that chat to ask, and
choosing ask or allow while it is on turns it off.
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
uses the browser's speech synthesis on plain text, and the composer borrows the
other half of the same browser: its microphone dictates into the message in the
browser's own language, keeping what was already typed in front of what is
heard. A browser with no recogniser says so on a microphone that stays off.

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
with Check, which answers for a key as it is typed as well as for the stored
one and keeps neither. A conversation is held with the model it names, chosen
in its own composer; the settings choose what a new conversation starts with,
and a model chosen in a composer becomes that choice as well, in the same
commit, so the last model picked anywhere is the next chat's. A conversation
naming a model the list no longer has falls back to the settings' choice
rather than refusing to answer. Each provider's reasoning must be
carried back inside a tool loop, and a test per provider proves it.

The September 2026 catalog update adds GPT-6 Astra, Sol and Luna, Claude
Opus 5.5, and Gemini 3.7 and 3.8 Flash. It replaces the retired DeepSeek V4
Flash API ID with `deepseek-flash` (V4.1 Flash) and migrates saved settings
and conversation choices to that ID. Historical run records retain the ID
they actually used. The catalog keeps older active models so an existing
selection remains usable. Model IDs, limits and image support were checked
against the [OpenAI model catalog](https://developers.openai.com/api/docs/models),
[Claude models](https://platform.claude.com/docs/en/models/overview),
[Gemini models](https://ai.google.dev/gemini-api/docs/models) and
[DeepSeek models](https://api-docs.deepseek.com/quick_start/pricing/).

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D141. One application space holds the conversations and the agent's settings

AI is the third application space beside Data and Dashboards, reached from the
status-bar space switch. Data panels remain mounted,
and detached panels remain visible, by the same covering contract as
Dashboards. Left column: New chat, history, Settings; settings replace the
conversation on the right. Its head can become a name filter for chats and
projects without changing the open conversation. New chat reopens an existing
unarchived "New chat" with no messages or runs before creating another one.
The transcript has a centered reading width. Agent steps use the same text size
as answers, with a quieter color; the composer sits on a raised surface below
the transcript. Copy and speech controls under a message appear on hover or
keyboard focus, and remain visible on touch screens. Unsent text is kept in
memory per conversation while this browser page is open, including when the
person switches application spaces or opens another chat. Sending clears it.
Down the left edge of a conversation with more than
one question is its contents: a mark per question, named by its first line,
which scrolls to it, and the one being read is drawn apart from the rest. The two cards have the ordinary draggable workspace
separator; the left card is remembered, collapsible and capped at 40% of the
space. Collapsed, it keeps New chat alone in its head and Settings at its foot. Keys, Model, Confirmations and the archive live here, not on
`/preferences`. Titles are written by the chosen model and renamed by pressing
the name above the conversation. A row of the history is pinned, which keeps it
above the rest, or archived, which takes it out of the history without losing
it, or moved into a project — a folder of conversations and nothing more,
created, renamed, collapsed and deleted in the history itself. A project
carries no instructions and no connections of its own, because a folder that
quietly changed how the agent answers would be a second place to look for that;
deleting one keeps every conversation it held, out of any folder. Nothing is deleted from a row: the archive in the settings restores a
conversation or deletes it, one at a time or all at once, which is the only
place anything is deleted. A pin survives archiving, so a restored conversation
comes back where it was. Content is encrypted at rest under `AI_CONTENT_KEY`.
No editing, tags, rewind, branches or transcript search.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D142. A message may carry the person's own files

The plus beside the composer offers the open tabs (D133) and files from the
computer: text and images, nothing else. A file is an image when its first
bytes are PNG, JPEG, WebP or GIF, whatever it is named or typed as, and text
when it reads as UTF-8 without a NUL; anything else is refused in a sentence
before a run exists. A message carries at most five files, an image up to
5 MB, text up to 256 KB, 10 MB together; the settings API sends these numbers,
the composer checks them before sending and the server again when it is sent.
Images are offered only to a model whose entry in D140's file reads them; an
image already attached when the model changes holds the message back until it
goes. A message may be a file alone, and then names the chat.

Unlike a tab, a file's content travels to the provider: text inside the
message, fenced and named, an image as the standard image block, and both stay
in the model's working state for later turns like the rest of the message. A
file is part of its message: stored with it in one commit, its name and bytes
sealed under `AI_CONTENT_KEY`, listed in the transcript without reading its
bytes, served only to the conversation's owner — an image as the type its bytes
showed, anything else as plain text — and deleted with the message. The
message travels as a form: its text, its tabs as one JSON field, its files.

Rejected: uploading a file before the message is sent, which leaves files
nobody sent to be swept; PDF and Office documents, drag and drop and pasting,
in this first version.

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D156. Experimental Jev policy decides each change

A conversation may choose Jev as its change policy only after its owner stores
a verified TypeSafe API key. The key uses the same encrypted per-person key store
as the chat model keys; it is never returned. Settings provide Check, replace
and Clear. Clearing a key leaves the conversation's selection visible, but
every later change fails closed until a valid key is stored again. The selector
shows the unavailable choice with a message pointing to AI settings.

Before each changing query or action, the server sends Jev the proposed action,
connection name and bounded preview. A `Noul` answer at least 0.5 allows it;
below 0.5 denies it. Missing answers, network errors and timeouts deny it.
The decision appears as a tool substep. Jev does not override connection access,
read-only connections or the third-party transfer flag. This conversation
policy takes precedence over the person's global allow-all setting.

This experiment pins `langchain-typesafe==0.0.1a3`; its interface is pre-release.
To roll back, revert the dedicated Jev commit. Stored conversations with `jev`
then read as `ask` through `policy_of`; old TypeSafe keys remain encrypted and
inert until explicitly cleared or removed by a later migration.

Spec: [Jev change-policy experiment](../decisions/2026-09-24-jev-change-policy.md)

## D157. Jev may select any compatible model within one provider

Each model group offers an automatic Jev choice when the person has both that
provider's key and a TypeSafe key. All catalog models of that provider are
candidates for each answer; models without image input are excluded whenever
the conversation has an image. The prior model stays as fallback, or the first
model in the new group if the person switched providers. A selection stores the
provider and fallback independently. The actual chosen model is recorded on
the run, shown beside its steps, and used for the whole run, its summary, and
its title. A paused run resumes with that same model. Jev sees only the latest
user text, truncated to 16,000 characters, plus provider and image presence.
It does not receive attachments, prior messages or tool results for routing.

If Jev fails, returns a model outside the candidates, or its key was removed,
the fallback answers. If the fallback cannot read an image, the first compatible
model in that provider answers. If no compatible model exists, the run is
refused. A server-side key and provider check prevents selecting an unavailable
auto choice through the API. The first UI selection warns about provider-wide
choice, different costs and TypeSafe transfer. Its Don't show again checkbox
uses the same per-user, per-server browser storage pattern as tab groups and
is remembered only when the person confirms.

The classification runs before the answer is recorded, and has a 10-second
limit. It uses the same `langchain-typesafe` dependency as D156, called directly
because its experimental middleware does not carry this application's per-user
key and fallback model. The database stores nullable `auto_provider` fields on
the person's preferences and each conversation; removing this feature requires
reverting the code and downgrading the migration.

Spec: [Jev model routing](../decisions/2026-09-24-jev-model-routing.md)

## D158. A separate quick chat answers without agent tools

Quick conversations and messages are separate tables, encrypted under
`ai_content`, owned by one person. The request calls the chosen
chat model directly, with a maximum 16,000-character request and at most 20
recent messages within an 80,000-character context budget, and no LangGraph agent,
workspace context or application tools. It uses the same provider keys and
catalog as the agent. The model cannot read application data through this path.

Selecting text in an agent message offers Add to chat and More details. Add to
chat quotes the selection in that agent conversation's unsent draft. More
details creates a quick conversation and immediately sends an explanation
request containing the selected text. The window opener accepts an intent,
independently of the AI space, so a later Data surface can call it with its
own selection. Selection is capped at 8,000 characters.

Spec: [Quick chat and selected text](../decisions/2026-09-24-quick-chat.md)

## D159. Quick chat opens from a global rail and shares the AI history list

The Quick chat button is a movable block on the workspace tool rails, available
from every space. It opens a new plain conversation in a floating window. The
opener reuses an untouched empty quick conversation from history before creating
another one, including when a different conversation is currently shown. The
window uses the agent conversation's transcript and composer layout, with a
model selector but without a history selector or New/Delete controls. Plain
conversations appear in the main AI chat history alongside agent conversations,
with the same row appearance and actions: pin, project and archive. The archive
in AI settings restores or permanently deletes either kind of chat; the history
does not delete chats directly. Selecting a plain conversation opens it in the
quick-chat window, while selecting an agent conversation opens it in the AI
space. Storage and execution remain separate from agent conversations and runs. The shared window
opener accepts a saved conversation ID as well as new and explain intents, so
future screens can launch the same window without owning it.

The window starts at 540 × 650 pixels, can be resized, and uses the same browser
speech recognition control as the agent composer. Dictation appends to the
current draft and stops when the window closes or a message is sent.

Spec: [Quick chat navigation](../decisions/2026-09-24-quick-chat-navigation.md)
