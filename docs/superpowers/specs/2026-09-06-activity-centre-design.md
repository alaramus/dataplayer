# Everything that needs a person

## Problem

Three unrelated mechanisms were telling one person about one application.

A coloured bar appeared at the bottom centre of the screen for four seconds and
then was gone: Quasar's `notify`, in Quasar's palette, in a position nothing
else in the application uses. If a person was looking at another monitor, or at
a dialog the bar was drawn behind, the message was never delivered. Nothing
recorded that it had been said.

A floating window called Processes held running work — the server's jobs and
this tab's own operations — and had to be opened deliberately by a button
labelled "Processes" that most of the time said nothing.

And a request for access to somebody's connection was a durable row that was
visible only inside the permissions page of that connection's window. The one
thing in the application that genuinely waits for a human answer was the one
thing with no place of its own.

The three have a single thing in common: each is the application needing
something from the person, or telling them something. They belong together.

## Shape

One button at the end of the status bar. One sheet along the right-hand edge,
three sections in it.

```
┌──────────────────────────────────┐
│ Activity              ⃝ DND  ✕   │
├──────────────────────────────────┤
│ NEEDS YOU                    (2) │
│  ● Ivan is asking for access     │
│    to prod-db          [Open]    │
│  ● Restore backup was interrupted│
│    by a restart        [Details] │
├──────────────────────────────────┤
│ WORKING                      (1) │
│  Start service · analytics-pg    │
│  pulling the image (1 of 6)      │
│  ▓▓▓▓▓░░░░░░░░░  [Cancel job]    │
├──────────────────────────────────┤
│ RECENT              [Clear all]  │
│  ✓ 2 rows brought in     12:04   │
│  ✓ Connection saved      12:01   │
└──────────────────────────────────┘
```

Why a sheet and not the floating window it replaces: a floating window is a
piece of work a person opened, moved and will come back to. This is the
application talking. It has no place in the window taskbar, it should not be
draggable, and there should never be two of it.

Why it overlays rather than pushes: the workspace is a tree of resizable
sections holding grids that measure themselves. Making the sheet part of the
layout means every open and close is a relayout of everything on screen, and
the whole point is to glance at it while work is running.

Why not modal, and why no scrim: a person opens this to watch something
progress. Dimming the application behind says the application has stopped.

## The three kinds

They are separated because they behave differently, not because they came from
different places.

| | Needs you | Working | Recent |
| --- | --- | --- | --- |
| Ends by itself | never | when the work ends | fades in seconds |
| Survives reload | yes — a server row | yes — a server row, or no | no |
| Counted on the button | yes | yes | no |
| Where it is answered | in the thing it is about | here | nowhere |

The count is the part most easily got wrong. A badge that includes every
"Copied" is a badge at a permanent double digit, and a number that is always on
is a number nobody reads. It counts what is waiting and what is running.

## What the button becomes

It already showed the current step and a progress bar, and that is the useful
half of it. Renamed from Processes to Activity, because "processes" describes
one of the three sections and the other two are not processes.

- nothing running, nothing waiting: a bell, no count;
- something waiting: a bell and a count, marked;
- something running: the step and the progress bar, as before, with the count
  beside it.

## Where a message goes

`useToast` is the one door every screen already uses — around a hundred calls,
none of them reaching Quasar directly, because ESLint forbids `useQuasar` in a
screen. So the whole change is behind that door:

```
screen → useToast → notices store ─┬→ sheet is open:  a row appears in Recent
                                   └→ sheet is shut:  a card, bottom right
```

No screen changes. What changes is where the card is drawn (bottom right, above
the button that owns the list, in our own tokens), how long it stays (success
and information fade, an error and an offer do not), and that it is still there
afterwards.

Two rules that came out of reading the existing call sites:

- **Above the window that raised it.** This application has no Quasar
  dialogs: what it calls one is a floating window (D14), and so is a
  confirmation. Most messages are therefore raised from inside something drawn
  over the page, and a card behind that thing is not a message at all. The card
  layer clears our windows, our own sheet and Quasar's menus — where Quasar's
  notifications used to be — and `layers.css` names it, so the exception is
  visible rather than discovered.
- **A ceiling on the stack.** Pasting a hundred rows can raise a message per
  failure. Three cards, then a line saying how many more are in the sheet.

Do not disturb belongs here for the same reason: during a long import the
person wants the outcome, not the commentary. It stops the cards and changes
nothing about the record.

## Why there is no notifications table

The tempting next step is a server-side notification with a read flag. It is
not built, and the reason is worth writing down so it is not "fixed" later.

The two things that must survive a reload already do, as their own durable
rows: a job is a row the server owns (D81) and an access request is a row that
waits until it is answered (D61). The sheet reads both. What would be added by
a table is the client's own log — "Row inserted", "Copied", "2 rows brought in"
— which is worth nothing ten seconds later, let alone after a reload, and which
would arrive carrying read-state, retention, pruning and a fan-out across a
person's open tabs.

If something later genuinely needs to be told to somebody who is not connected,
that is a durable row of its own kind, like a request, and it appears in the
first section through a source. Not a general-purpose inbox.

## Attention as sources

The first section is the one that will grow: today three kinds, and every
future capability that can leave something unresolved wants a place in it.

```ts
export interface AttentionItem {
  id: string
  tone: Tone
  title: string
  detail: string
  at: number
  action: { label: string; run: () => void } | null
  dismiss: (() => void) | null
}
```

A source is a composable a feature exports that returns those. `sources.ts`
lists the sources; the panel draws items and knows nothing about jobs, shares
or connections. Adding a kind is a composable plus a line, which is the rule
the whole application follows for adapters, panels and job kinds.

Three at the start:

- **Access requests waiting on connections I own.** Needs one backend change:
  `GET /shares/requests` takes `connector_id` and requires it, so there is no
  way to ask "everything waiting on me". It becomes optional. Owner-scoped
  exactly as it is now — the question is only asked across the connections the
  asker owns.
- **Jobs that failed or were interrupted.** Already in the listing the panel
  reads. An interrupted job in particular is invisible today: it is what a
  restart leaves behind, and nobody is told.
- **Connections that answered badly.** From the health reports the socket
  already pushes. Reports what is known, probes nothing.

## Testing

- pure: the log's trimming and unread rule; the count; which of a set of jobs
  is outstanding; the wording of each item. All without mounting.
- component: the panel draws three sections; a dismissed notice leaves; an
  access-request item opens the connection window rather than answering in
  place.
- browser: a message raised inside a dialog is visible; the sheet opens over a
  floating window; a running job shows in the sheet and in the button; the
  sheet does not reflow the workspace.

The last group is not optional. A green unit test about a notification that is
drawn underneath a dialog is exactly the failure this project has already had
once, with the captions in the catalog tree.

## Migration

`.q-notification` appears in sixteen assertions across seven end-to-end files.
They become one helper in `tests/utils`, so the next change of this kind is one
edit rather than sixteen.
