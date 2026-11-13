# Search

One search finds what you can see in DataPlayer: connections and what is
inside them — tables, files, keys, topics — and what the application keeps for
you: saved queries, pipelines, dashboards, chats, services, SSH keys, open tabs
and tab groups, kinds of source and pages of this guide.

## The search field

The field in the header, **Search everything**, opens the search. Ctrl+K (⌘K on
a Mac) does the same from anywhere but a terminal.

- Results appear while you type, grouped: open tabs, connections, one group per
  connection, favorites, pipelines, dashboards, conversations, services, SSH
  keys, the guide, kinds of source. **Best matches** come first.
- A name matches when it holds every word you typed, in any order, whatever the
  case. An exact name or one that begins with your first word ranks above one
  that only contains the words.
- While typing, slow places are not asked. **Enter** searches everything,
  waiting for each connection as long as it may.
- Each place says what happened to it: nothing found, did not answer in time,
  cannot be reached, switched off, locked. Some offer a gesture — **Try again**,
  **Search anyway**, **Unlock the SSH key**.
- **Ask the agent**, at the end of the list, opens a new chat with your words in
  it, not yet sent.
- An empty field shows recent searches and what you opened lately.

Pressing a result opens it where it lives: a table in the workspace, a
pipeline in Pipelines, a chat in the AI space, a guide page in the guide's
window. **Show in catalog** finds a table or file in its catalog instead.

## Searching one connection

Opened while a catalog has the focus, the search offers
**Search in ‹connection›** first: the right arrow takes it, Backspace removes
it. The catalog's own filter does the same for one level, and its search button
for everything below it.

## The Search tab

**Show all results**, or Enter, opens the Search tab in the work column. It
holds the whole answer and filters it by group, connection, kind and the date
something changed.

**Search inside files** reads the text of every file below the connections you
tick. It can take minutes, skips binary files and files over 8 MB (1 MB over
SSH), and runs in the background; what it finds arrives as it goes, and
**Stop** keeps what was found so far.

## The search index

A connection with many names answers slowly when it is asked every time. Its
owner can keep a list of its names on this server instead:
**Search index…** in the catalog's actions menu, the **Search index** tool on
the bottom left rail, or the connection window's **Options** page.

- **Keep a list of names for search** copies the names of tables, keys,
  folders and files into this server's database as plain text, read with the
  owner's credentials. Switching it off deletes the copy.
- **Read again within** — 1 hour, 6 hours, 1 day or 1 week — says how old the
  list may be before the search asks the source instead. **Read now** reads it
  at once.
- **What files hold**, for a folder, keeps the text of the files below it too,
  so a word inside them is found on Enter without opening them again.
- Only the owner switches it on; a person the connection is shared with sees
  the state.

Where this server runs the model for it, a kept list is also searched by
meaning: on Enter, rows marked **By meaning** add what the words alone missed.
