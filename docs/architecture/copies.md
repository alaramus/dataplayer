# The copy history

What a person copied in the application, kept on the server for them to copy
again or delete. Read this before adding a copy button, changing
`shared/clipboard.ts` or the window on the right rail.

Decisions here: D460.

## What exists today

```
backend/app/users/copies.py        the table, its limits, list, record, delete
backend/app/users/copy_routes.py   /copies: list and search, one whole, record, delete
frontend/src/shared/clipboard.ts   copyText and the one listener it tells
frontend/src/features/copies/
├── record.ts          the listener: sends a copy to /copies, installed by main.ts
├── api.ts             the list, one copy's whole text, deleting
├── copies.ts          the window's state and its lines (pure)
├── CopiesCommand.vue  the button on the right top rail
└── CopiesWindow.vue   the window, drawn once by WorkspacePage
```

## D460. Every copy the application makes is kept, except a secret

- **One boundary.** A screen copies only through `copyText(text, origin)`,
  and the origin is required: either where the text came from — a closed set,
  `CopySource`, and an optional detail such as a column — or `{ secret: true }`.
  A password, a token, a key, an invitation link, a connection string and a
  value a view hides are secrets and never leave the browser. A new copy
  button decides which it is, because it cannot compile without.
- **Copying from the history does not reorder it.** Copy again in the window
  uses `{ history: true }`, which is not kept: the row stays where it is
  rather than jumping to the top under the pointer. The same text copied
  anywhere else in the application still moves to the top.
- **Only the application's copies.** A person's own Ctrl+C on selected text
  is not heard, nor are catalog nodes held for pasting into another
  connection, which are not text.
- **On the server, per person, unencrypted.** The history follows the account
  across browsers. It is text the person already had on their screen, so it
  is stored as text, unlike a connection's secrets.
- **Bounded.** 65 536 characters of a copy are kept and a longer one is
  marked cut; the browser sends one character more than that and no more.
  The newest 500 copies of a person are kept. The same text copied again
  moves to the top rather than standing twice.
- **The list carries the start.** Listing returns 300 characters of each copy
  and its length; copying one again asks for the whole text. Search is a
  case-insensitive substring on the server, `%` and `_` read as letters.
- **Recording is quiet.** It happens after the browser took the text and is
  never awaited by the copy: a failure leaves the clipboard as asked and says
  nothing. Nothing is sent before sign-in.
- **The window** opens from the right top rail. One copy is deleted with its
  button and no question; the ticked ones, or all of them, after a
  confirmation. Ids a search or another tab already took away are not sent.

Spec: [A copy history](../decisions/2026-11-27-copy-history-design.md)
