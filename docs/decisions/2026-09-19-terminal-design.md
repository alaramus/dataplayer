# A terminal on an SSH connection

Date: 2026-09-19. Decisions: D148, D149.

Status: implemented with this specification.

## What was asked

A terminal that works per source: for SSH a shell on the remote server, for
personal storage a shell over one's own files. It opens from a rail button,
as Services does; pressed while a connection is open it connects to that
connection, and otherwise the person chooses one. The terminal for personal
storage was postponed by the owner; SSH comes first. Asked in the same plan
and answered by the owner: only the owner of a connection may open a
terminal on it.

## The old application

- The terminal was a command on the application's one public socket, next to
  data requests and agent output.
- It ran a local `ssh` process in a pty on the application server. The key
  was written to a temporary file and removed on a timer, a password went
  through an askpass script, and each user had an `ssh-agent`.
- Closing the pty's master while the child still held the slave end hung the
  whole server on macOS; the code carries a long comment about killing the
  process tree first and closing off the event loop.
- Host keys were accepted on first sight (`StrictHostKeyChecking=accept-new`).

## What was decided

**D148 — a socket of its own.** `WS /api/v1/terminals`, one per terminal.
Authenticated by its first frame as the application's socket is (D18), with
the connection and the size in the same frame. Binary frames carry
keystrokes and output; text frames carry the resize, `ready`, `refused`,
`ended` and a notice for a frame that was not understood. It never
reconnects.

Why not a topic on the shared socket, as D18 would suggest:

1. A topic is announced to subscribers. A terminal is one screen's
   conversation with one shell.
2. The shared socket reconnects and restates its subscriptions. A reconnected
   terminal is a new shell, and handing one over silently in place of the
   shell somebody was typing into is the wrong answer; saying it ended and
   offering another is the right one.
3. Every keystroke and every chunk of output would be base64 inside JSON.
4. One terminal's output would queue in front of every other topic.

D18 rejected a route per need because each would repeat authentication and
reconnection. Authentication is repeated here in twenty lines; reconnection is
exactly what a terminal must not have.

**D149 — the owner's, as long as the socket, no program here.**

- The socket asks `own`. A grant is access to the data a source holds; a shell
  is the account the connection signs in as.
- A driver capability, `SupportsTerminal`: a running shell as bytes both ways
  and a size. The SSH driver opens its own connection, asks for a pty of the
  browser's size with `TERM=xterm-256color`, and starts the login shell with
  standard error joined to output. No local process, no key on disk, and so
  none of the old application's pty traps.
- The kept connection of the source is not used: it is made again when the
  server drops it, which would take a shell with it, and a terminal's
  lifetime is the person's, not the pool's.
- Nothing is kept after the socket closes; there is no reattach. The screen
  says the shell ended or the connection was lost, and offers to open again.
- At most eight open per person, counted in the process.
- On the client the terminals and their xterm screens live in a module, and a
  view lends a screen its element while it is on screen: the panel shows one
  tool at a time, and showing Services must not end a shell.
- The rail button follows D143: pressing it while its tool is shown hides the
  panel. Otherwise, in a connection with a shell it brings that connection's
  latest terminal forward or opens one; anywhere else it shows the panel,
  which lists one's connections that have a shell.
- A refusal because the key is locked offers to unlock it (D147) and opens the
  terminal again once it is.

## Left for later

- A terminal on personal storage — a second driver implementing the same
  capability.
- Starting in the connection's folder rather than the home: it needs a `cd`
  typed on the person's behalf, or a shell started with a command.
- Ending an open terminal when its key is locked.
- Reattaching to a shell after a dropped network, which would need a
  multiplexer on the server or shells that outlive their sockets here.
