# A copy history

Asked for: every person keeps a history of what they copied in the
application, opened as a window from a button on the right top rail, where one
copy, several or all of them can be deleted.

## D460. Every copy the application makes is kept, except a secret

`shared/clipboard.ts` was already the only way a screen wrote to the
clipboard, and said that a copy history would attach there. It does: after the
browser took the text, `copyText` tells one listener, which the copy history
installs at start-up. A setter rather than an import keeps the shared module
below every feature that copies.

**Secrets.** About a third of the copy buttons copy something that opens a
door: a service's password, an MCP token, a metrics agent's key and the compose
file carrying it, an invitation link, a connection string a person may have
typed a password into, a value a view hides until asked. Kept in a table, each
would be a credential at rest in plain text, readable by anyone with the
database. So the origin is a required argument, `{ from, detail }` or
`{ secret: true }`; a secret never reaches the listener. Required rather than
defaulting to "keep", because the default would be wrong exactly for the
button somebody forgot.

**Where from.** A closed set of sources rather than a sentence, so the window
words it in the reader's language today, not the one they copied in. The
optional detail is the screen's own name for the thing, such as a column.

**Server rather than the browser.** The history is a person's, and a person
signs in from more than one browser. localStorage would also hold it for
whoever uses that browser next.

**Not encrypted.** Considered and declined by the owner: it is text the person
already had on their screen, not a credential, and encrypting it would push
search to the browser.

**Limits.** 65 536 characters of one copy and the newest 500 copies. A whole
grid copied may be megabytes; the browser cuts what it sends to one character
past the limit, so the server can still say the copy was cut, and nothing more
travels. A repeated text moves to the top instead of filling the list with
copies of one value copied back and forth.

**What is not kept.** Ctrl+C on text selected in the page: heard through the
document's `copy` event it would fill the history with fragments nobody meant
to keep. Catalog nodes held for pasting into another connection are not text.

**The window.** A search over the text, a list newest first showing three
lines of each copy with its source and time, Copy again and Delete on each,
tick boxes with Delete selected, and Clear history. One delete is not
confirmed; several and all are. Copy again is not kept a second time: tried
first, it moved the row to the top under the pointer while the person was
still working in the list, so a third origin, `{ history: true }`, copies
without telling the history.
