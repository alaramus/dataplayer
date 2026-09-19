# Terminals

A shell on the machine a source runs on, typed into from the panel at the foot
of the workspace. Read this before changing how a terminal is opened, what
travels on its socket, or who may have one.

Decisions here: D148, D149.

```
backend/app/
├── adapters/
│   ├── terminal.py        TerminalSize, Terminal, SupportsTerminal
│   └── ssh/terminal.py    the login shell of the account, in a pty on the server
└── terminals/
    ├── messages.py        the text frames: open, resize, ready, refused, ended
    ├── slots.py           how many terminals each person holds
    └── routes.py          the socket: who is asking, then bytes both ways

frontend/src/features/terminals/
├── frames.ts              the text frames, written out again
├── terminalLink.ts        one terminal's socket, never reconnecting
├── terminals.ts           where a terminal opens, what it is called, what is said
├── useTerminals.ts        the terminals of this browser tab, and their screens
├── TerminalView.vue       lends a screen an element while it is shown
├── TerminalsTool.vue      the tool of the panel: tabs, the one in front, a choice
└── TerminalCommand.vue    the rail button
```

```
WS     /api/v1/terminals
```

Only SSH has a shell today. A terminal on personal storage was asked for and
postponed; it would be a second driver implementing `SupportsTerminal`, and
nothing above the adapter would change.

## D148. A terminal is a socket of its own

Every other thing the server says without being asked travels on the one
socket (D18). A terminal does not, and the reasons are what it carries:

- **It is one conversation, not a topic.** A topic is announced to whoever
  subscribed; a terminal's output belongs to one screen, and its input comes
  from that screen alone.
- **It must not reconnect.** The application's socket reconnects and restates
  its subscriptions, which is right for a topic and wrong here: a new socket
  is a new shell on the server, and quietly handing a person a fresh shell in
  place of the one they were typing into is worse than telling them it ended.
- **It is bytes.** Keystrokes and output are binary frames; on the shared
  socket each would be a JSON frame with the bytes in base64.
- **It is heavy.** A `cat` of a large file would queue in front of every
  health dot and job step on the shared socket.

What it keeps from D18 is authentication: the socket opens unauthenticated and
its first frame, within `WS_AUTH_TIMEOUT_SECONDS`, carries the token together
with the connection and the size, because a token in the address is written
into access logs and browser history. After `ready`, binary frames are the
shell's both ways and a text frame says the window changed size. `refused`
and `ended` are each followed by the server closing the socket.

The frames are written out on both sides by hand, as the application's are:
OpenAPI has no WebSocket channel.

Rejected: a topic per terminal on the shared socket. It keeps one socket per
tab, and in exchange puts base64 around every keystroke, lets one terminal's
output hold up everything else, and needs the reconnect of the shared socket
switched off for exactly these frames.

Spec: [A terminal on an SSH connection](../decisions/2026-09-19-terminal-design.md)

## D149. A terminal is its owner's, lives as long as its socket, and runs no program here

- **Only the owner.** Typing into the server as the account the connection
  signs in as is more than any grant gives: `structure` lets a person change
  tables, not run `rm -rf` on the machine. The socket asks `own` of the access
  check (D33), and the screen offers only one's own connections.
- **A capability of the driver.** `SupportsTerminal` hands back a running shell
  as bytes each way and a size it can be told; a screen asks for it by the
  `terminal` capability code. The socket knows nothing of SSH.
- **The shell runs on the server, not here.** The SSH driver asks for a
  pseudo-terminal and the account's login shell over its own connection —
  never the kept one, which is made again whenever the server drops it and
  would take the shell along. The old application ran `ssh` in a local pty
  with the key written to a temporary file and an askpass script for the
  password; here no process is started and no key touches the disk.
- **Nothing outlives the socket.** Closing the terminal, closing the page or
  losing the network closes the shell and its connection. There is no
  reattaching: what a person sees after a drop is that it ended, and a button
  to open another.
- **Eight at a time per person**, counted in the process (D124). Each is a
  signed-in connection and a shell on somebody's server.
- **The screen outlives its view.** The panel shows one tool at a time, so the
  terminals and their screens live in a module of the page; switching to
  Services and back keeps the shell and its scrollback. Signing out closes
  every terminal.

Known deviations:

- **Locking a key does not end a terminal already open.** The passphrase is
  asked for when the shell signs in (D147); after that the session is the
  server's, as it is for an `ssh` client once an agent is locked. The catalog
  and the reader ask on every use and stop at once.
- **The shell starts in the account's home**, not in the folder the connection
  browses from: moving it there would mean typing a `cd` into the shell on the
  person's behalf.
- **The count is per process**, correct only while the backend is one (D124).

Spec: [A terminal on an SSH connection](../decisions/2026-09-19-terminal-design.md)
