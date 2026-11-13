# Preferences and your account

**Preferences**, in the user menu at the top right, holds what belongs to you
rather than to one connection. **Sign out** is in the same menu.

## General

- **Language**: the language of the whole interface. It is kept with your
  account, so it follows you to any browser. Until one is chosen, the browser's
  own is used.
- **Appearance**: a light or dark theme, or **System**, which follows the
  operating system. Kept with your account.
- **Reading voice**: the voice that reads messages aloud. Voices are the
  browser's own, so this is kept in this browser.
- **Personal storage**: how much of your own files on this server you use,
  against the limit an administrator set.

## Connections

**How often connections are checked**: every connection is probed on this
schedule while a workspace is open, and the dot beside it in the list says what
the last answer was. **Never** checks only when you ask. A slow or distant
server is worth asking less often.

## SSH keys

The keys your SSH connections sign in with. More about them is on the
[SSH](source-ssh.md) page.

- **New key** makes one on this server, where it stays. **Copy the public key**
  and add it to `authorized_keys` on the servers it should open.
- **Import** brings in a key you already have.
- A key can keep its passphrase, have none, or ask for it. One that asks is
  **Locked** until you **Unlock** it for 15 minutes, 1 hour or 8 hours; **Lock it
  now** locks it again.
- A key used by a connection cannot be deleted until its connections use
  another.

## Tours

The welcome tour and short tours of each part of DataPlayer — a table read
other ways, a pipeline, dashboards, the agent. **Take** starts one, **Again**
repeats one already taken. A tour makes a practice database for itself and
takes it away at the end.

## MCP access

Tokens with which an AI agent outside DataPlayer, such as Claude Code, Cursor or
Codex, works with your connections. How to make one is on
[The AI agent](assistant.md) page.

## Administration

An administrator also has **Admin** in the user menu, with **Users**:

- **New user** makes an account. It waits for a password: **Link to set a
  password** gives a link to send the person, which works once and for a
  limited time. The same link resets a forgotten password.
- **Edit this account** changes the name, whether the person **Can sign in**,
  whether they are an **Administrator**, and their **Storage limit**.
- **Delete this account and all it owns** removes the person with their
  connections and their files.

An administrator manages accounts, not other people's data: they do not see
other people's connections.
