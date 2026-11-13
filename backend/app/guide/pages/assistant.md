# The AI agent

The agent answers in the **AI** space of the switch at the top of the left rail.
It works through your connections as you do: it lists them, finds and reads
tables and files, runs queries and actions, opens things in the Data space,
draws charts — and reads this guide to answer questions about DataPlayer
itself. A change it wants to make is asked about first.

## Before the first chat

The agent works with your own key of a model provider: Anthropic, OpenAI,
Google, DeepSeek and others.

1. Open the AI space and **Settings**.
2. Choose a model. The key icon beside it opens the provider's key: paste it,
   **Check** it, save it. One key serves every model of that provider.
3. The model chosen in Settings is what a new chat starts with. Each chat can
   choose another in its own composer.

## A chat

- **New chat** starts one. Type in **Message the agent** and **Send**; the
  microphone dictates instead, where the browser can listen.
- While it works, the agent's steps are shown one by one: what it read, what it
  ran, how long it took. **Stop** ends the answer.
- Answers are formatted text, with tables, charts and diagrams. Each can be
  copied or read aloud.
- Selecting words in an answer offers **Add to chat**, which quotes them in
  your next message, and **More details**, which asks the quick chat to
  explain them.

## What it knows

The agent does not see your screen. To point it at something, **Attach tabs
or files**:

- **Workspace tabs…**: up to five open tabs — a table, a catalog, a query, a
  result — for the next message;
- **Files from computer…**: text files, and PNG, JPEG, WebP or GIF images for a
  model that reads images.

Without an attachment it finds things by name with search. When several
connections match a name, it asks which one.

## Changes

**Changes**, in the composer, says what the agent may change in this chat:

- **Read only**: nothing is changed from this chat;
- **Ask before changes**, where every chat starts: a change waits for your
  answer on a card with **Allow once**, **Allow all changes in this chat** and
  **Allow all changes in every chat**. The card shows what would change — the
  statements, what a drop would take with it;
- **Allow changes**: changes in this chat run without asking;
- **Let Jev decide**: Jev, a separate service with its own key, decides before
  each change;
- **Allow all changes in every chat** is a setting of yours, not of the chat.
  It is turned off again in **Settings** under **Confirmations**.

A chat waiting for your answer is listed under **Needs you** in the activity
bell. A connection set to **Read only** for consoles is never written, and a
level of access you do not have is never used.

## Which connections it may read

The agent reads a connection only when its owner switched on **Allow sending
data to third parties** on the connection's **Permissions** page: what it reads
is sent to the model provider. Otherwise the agent sees the connection's name
and type and nothing else. The owner can allow it from the refused step; a
person the connection is shared with is told to ask the owner.

Switching the setting off later removes what was read from that connection
from the chat's further answers.

## Chats, projects and the archive

- The list of chats has **Pinned** chats at the top and a filter by name.
- A chat can be pinned, moved into a project, renamed and archived.
- **New project** groups chats. Deleting a project asks whether its chats go
  back to the list or into the archive.
- **Archive**, in Settings, restores archived chats or deletes them for good.

## Model choice by Jev

Instead of a model, **Choose with Jev** lets Jev pick one for each answer from
the models whose keys you set. Your request is sent to TypeSafe, Jev's
provider, to make the choice. It needs a Jev key, set in Settings.

## Quick chat

**Quick chat**, at the top of the left rail, opens a window for a plain
conversation with a model from any space. It has no tools and cannot read
anything in DataPlayer. In Chrome on a desktop computer it can be answered by
Gemini Nano, which runs on your own computer once Chrome has downloaded it, so
nothing leaves it. Quick chats appear in the same history as the agent's chats.

## An outside AI agent

An agent outside DataPlayer — Claude Code, Cursor, Codex and others — can
work with your connections through DataPlayer's MCP address.

1. **Preferences**, from the user menu, then **MCP access**.
2. **New token**: a name, **Read only** or **Full access**, and when it
   expires. **Read only** reads catalogs, rows and queries and refuses every
   change; **Full access** changes data and runs actions without asking.
3. Copy the token: it is shown only once. The window also gives the line or the
   file entry that sets up the chosen client.

The outside agent has the same tools as this one, this guide included, and
reads only connections whose owner allows sending data to third parties.
**Revoke this token** cuts it off from its next call.

## Limits

- One answer makes at most 50 tool calls; ask a narrower question past that.
- A read returns at most 20 rows a time.
- A message carries a limited number of files of a limited size; the composer
  says which limit was reached.
