# The application agent

An agent that works on a person's data through the connections they added: what
it may do, how it asks, and how an answer runs and is shown. Which models it
uses, whose key pays and Jev are in [ai-models.md](ai-models.md). Read this
before adding a tool, before sending a connection's data to a model provider,
and before changing the chat window.

Decisions here: D133, D134, D135, D136, D137, D138, D139, D141, D142, D158, D159, D223.

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
D134: `list_connections`, `search`, `browse_catalog`, `describe_node`, `read_rows`,
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
├── AiMessageActions.vue copy and read aloud under a message, in either chat
├── AiMessageFiles.vue  the files a sent message carried, read with the person's token
├── AiSettings.vue      provider keys, model, confirmations and the archive
├── ChatMarkdown.vue    the D50 renderer in streaming mode
├── attention.ts        a waiting conversation as a Needs-you item (D113)
├── api.ts              vue-query ownership of server state
├── attachments.ts      which picked files join a message, by the server's rules
├── context.ts          which open panels a chip may name, and the open intent
├── dictation.ts        the browser's recogniser behind the composer's microphone
├── outline.ts          the questions of a conversation, and which one is being read
├── streaming.ts        open-fence protection while an answer streams
└── state.ts            selected-chat restoration and a chat requested from outside; the shared space store remembers AI
```

```
frontend/src/features/speech/
├── ReadAloudButton.vue the listen button of chats, documents and files
├── VoiceSelect.vue     the reading voice, in Preferences and AI settings
├── readAloud.ts        the one voice of the browser, shared by every reader and keyed by it
├── speechText.ts       prose without the marks around it, for Markdown only
└── voices.ts           the browser's voices, arriving after the page
```

```
src/stores/voice.ts     the chosen reading voice, kept in this browser
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
DELETE /api/v1/ai/projects/{project_id}?chats=keep|archive
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

`search` (S10, `app/ai/search_tool.py`) asks the one search (D197) as the
agent: only the providers that say `offered_to_agent` (D199), and only
connections whose owner allows transfer, so a closed one is not even matched by
name. It looks inside only the connections of the tabs attached to the message
being answered and those the model names, at most eight; a named one that does
not allow transfer comes back as D135's refusal and nothing else of it. At most
50 hits, each with the ids the other tools take. The result lists its
connections and is withheld like any other once one stops allowing transfer.

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
Which voice reads is the person's choice, kept in this browser and chosen in
Preferences or AI settings — one store serves both controls, so either one is
the choice everywhere; without one the browser reads in its default voice.
The same button reads a Markdown document and whatever text a panel shows,
whole and in that voice; code reads as it is rather than stripped of its marks.

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

## D141. One application space holds the conversations and the agent's settings

AI is the third application space beside Data and Dashboards, reached from the
status-bar space switch. Data panels remain mounted,
and detached panels remain visible, by the same covering contract as
Dashboards. Left column: New chat, history, Settings; settings replace the
conversation on the right. Its head can become a name filter for chats and
projects without changing the open conversation. New chat opens a local draft;
the conversation enters history when its first message is sent. Closing an
untouched draft leaves no history entry. When the active agent history is empty,
entering the AI space opens that draft directly. An empty chat offers a few
questions the agent's tools can answer, and pressing one sends it; they step
aside once somebody types or attaches a file.
The transcript has a centered reading width. Agent steps use the same text size
as answers, with a quieter color; the composer sits on a raised surface at the
foot of the card, and the transcript scrolls the card's whole height and passes
under it, stopping its last message above it; the quick chat is laid out the
same way. Copy and speech controls under a message appear on hover or keyboard
focus, and remain visible on touch screens; the quick chat has the same two
under its messages. Reading one message aloud stops any other, in either
chat. Unsent text is kept in
memory per conversation while this browser page is open, including when the
person switches application spaces or opens another chat. Sending clears it
after the server accepts the message.
Down the left edge of a conversation with more than
one question is its contents: a mark per question, named by its first line,
which scrolls to it, and the one being read is drawn apart from the rest. The two cards have the ordinary draggable workspace
separator; the left card is remembered, collapsible and capped at 40% of the
space. Collapsed, it keeps New chat alone in its head and Settings at its foot. Keys, Model, Confirmations and the archive live here, not on
`/preferences`. Titles are written by the chosen model and renamed from the
pencil beside the name above the conversation, in a window, as a dashboard is.
A dot before each name in the history is read off the chat's newest run: an
empty ring, grey and pulsing while the agent works, yellow while it waits for
an answer, red when the latest answer failed or was cut off by a restart, until
the next message. A quick chat has no run of its own and keeps the ring. A row of the history is pinned, which puts it
in the Pinned folder at the top, folded like a project; a pinned chat is never in
a project — pinning takes it out of one, moving it into one unpins it, and the
server refuses both at once. Or a row is archived, which takes it out of the history without losing
it, or moved into a project — a folder of conversations and nothing more,
created, renamed, collapsed and deleted in the history itself, which draws a
line between the Pinned folder, the projects and the chats in no folder. New chat
on a project's row opens a draft named after it, and the chat is made in that
project when its first message is sent. A project carries no instructions and no connections of its own, because a folder that
quietly changed how the agent answers would be a second place to look for that;
deleting one asks where the conversations it held go — to the history, out of
any folder, or to the archive — and loses none of them. Nothing is deleted from a row: the archive in the settings restores a
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
request: the ask, then the selection quoted once. The conversation is named by
the selection, set by the window, rather than by the first line of the
question, which would otherwise have to repeat it. The window opener accepts an intent,
independently of the AI space, so a later Data surface can call it with its
own selection. Selection is capped at 8,000 characters.
An empty quick chat is a local draft. Its first send creates the stored chat;
the question is committed before the model call, so a model error leaves the
question in history for a follow-up. What the model had already written is kept
as its answer when the provider fails on the way — Gemini answers "high demand"
with a 503 in the middle of a stream — and the error says so. A model that sends
nothing for 60 seconds is given up on; one that keeps writing is let go on for up
to 5 minutes. Stop cancels the writing, which this process tracks per chat
(D124), and the send keeps what was written as the answer, with no error. The answer streams on the `ai.quick`
topic as it is written, beside the agent's `ai.runs` rather than on it, whose
listener re-reads the list of conversations on every event; the send still
returns the saved chat, which is the authority, so a missed delta costs a
moment of text and nothing else.

Spec: [Quick chat and selected text](../decisions/2026-09-24-quick-chat.md)

## D159. Quick chat opens from a global rail and shares the AI history list

The Quick chat button is a movable block on the workspace tool rails, available
from every space. It opens a new plain conversation in a floating window. The
window remains a local draft until its first message is sent. It uses the agent
conversation's transcript and composer layout, with a
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

## D223. The quick chat may be answered by the model Chrome runs here

The quick chat's model list ends with a "This browser" group holding Gemini
Nano, reached through Chrome's Prompt API; the agent does not offer it. The row
says what Chrome reports and cannot be chosen where Chrome has no API or the
computer is below its requirements. While the model is still to be downloaded,
a line above the composer offers Download — Chrome starts it only from a press
— and then shows its progress; sending waits for `available`.

The server never calls it. `browser-turns` keeps the question as a provider send
does and returns the prompt and the trimmed history it would give a provider;
`browser-answers` keeps what the browser wrote, and only while a question waits.
The chat's model is `browser:gemini-nano`, the history is the one every quick
chat shares, and what was written before a failure is kept (D158). While it
writes, Send becomes Stop; what was written by then is kept as the answer. A history
too long for Nano's window loses its older half until it fits, the instructions
kept. The settings name only models the server can call, so the choice is not
remembered there (D140); the browser remembers that the quick chat was last on
it.

Spec: [Quick chat with the browser's model](../decisions/2026-10-11-quick-chat-browser-model.md)
