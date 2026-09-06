# What needs a person

Everything the application has to say to whoever is using it: work that is
running, a message about something that just happened, and a thing that will
not resolve itself until somebody answers it. Read this before adding a
notification, before making something ask for attention, and before putting a
count on a button.

Decisions here: D113, D114, D115.

## What exists today

```
frontend/src/shared/notifications/
├── notices.ts     the log, what is on screen, do-not-disturb
├── attention.ts   the shape of a thing that needs an answer
└── ToastHost.vue  the cards, bottom right, while the sheet is shut
frontend/src/shared/ui/useToast.ts      what every screen calls
frontend/src/features/activity/
├── ActivityIndicator.vue   the button at the foot of the screen
├── ActivityPanel.vue       the sheet, and its three sections
├── ProcessList.vue         the rows of the working section
├── attention.ts            a job nobody was told about
├── sources.ts              which features supply the rest
├── presentation.ts         a job or a local operation as a row
└── api.ts                  the jobs listing
frontend/src/features/shares/attention.ts       who is waiting for access
frontend/src/features/connectors/attention.ts   what stopped answering
```

## D113. What needs a person is one place, with three kinds in it

The old application had no such place at all: a running import announced itself
in a coloured bar that vanished after four seconds, and a request for access to
a connection was visible only to somebody who happened to open the right
dialog. Whether you were told something depended on where you were looking.

The screen now has one place for all of it, opened by one button at the end of
the status bar. It is a sheet along the right-hand edge rather than a floating
window: a floating window is a piece of work, and this is the application
talking about the work.

Three sections, in this order, because they are three different things and a
single list makes the important one unfindable:

- **Needs you.** A thing that stays until somebody deals with it: a request for
  access to a connection, a job that failed or was interrupted, a connection
  that stopped answering. Nothing here disappears on a timer.
- **Working.** What is running now, with its step and its controls — the
  server's own jobs (D81) and the operations this tab is carrying out.
- **Recent.** What happened. Trimmed, dismissible, and of no consequence.

Consequences:

- **The count on the button is only the first two sections.** An unread
  "Cell updated" is not a reason to mark a button, and a badge that counts
  everything is a badge people stop reading — which is the failure mode of
  every notification centre that has one.
- **The button says the most urgent true thing.** Idle, it is a bell and a
  count. While work is running it is the current step and its progress, which
  is what it already was and the reason it earns its place in a status bar.
- **The sheet leads to the answer; it does not hold it.** A request for access
  is answered in the connection's own window, beside the grants, because that
  is where the rule about answering lives (D61) — the sheet opens it. A second
  copy of an answering form is a second thing to keep in step, and D112 already
  says a thing's commands belong to the thing.
- **It floats over the work rather than moving it.** Opening the sheet does not
  reflow the workspace: a grid that re-measures every time somebody glances at
  a notification is a grid that jumps under the hand. Not modal either, and no
  dim behind it — the point of the sheet is to watch progress while carrying
  on, so Esc and a click outside close it and nothing is blocked while it is
  open.
- **The processes window is gone.** What it held is the "Working" section.

Known deviations:

- **A connection that stopped answering is only noticed while it is watched.**
  The server probes on subscription (D18), so this source reports what is
  already known and starts no probe of its own.

Spec: [Everything that needs a person](../superpowers/specs/2026-09-06-activity-centre-design.md)

## D114. A message is recorded first and shown second

Every screen already says what happened through one function, `useToast`, and
that function used to call Quasar's `notify` — bottom centre, in colours of its
own, four seconds, then gone forever. Anything a person missed while looking at
another monitor was simply not said.

A message is now written into a log first. The card that slides in at the
bottom right is what the log does when the sheet is shut; when the sheet is
open the message is a new row in it. The screens did not change: `useToast` has
the same four functions, and roughly a hundred calls stayed as they were.

- **Errors do not vanish.** Success and information fade; an error and an offer
  to act stay until dismissed, and both are in the log afterwards either way.
- **At most three cards.** The rest are already in the sheet, and the stack
  says how many.
- **Do not disturb suppresses the cards, never the record.** While a large
  import is running, a person wants the result, not sixty interruptions.
- **The log lives in the tab, not on the server.** The two things worth
  surviving a reload are already durable rows that the sheet reads — jobs (D81)
  and access requests (D61) — and a five-minute-old "Row inserted" is worth
  nothing after a reload. There is no notifications table, and inventing one
  would bring read-state, retention and pruning with it.
- **A card is drawn above everything.** What this application calls a dialog
  is a floating window (D14), and most of its messages are raised from inside
  one — a connection's form, an action's dialog, a confirmation. A card under
  the window that raised it is a message nobody receives, so the card layer
  clears our windows, our sheet and Quasar's menus, which is where Quasar's own
  notifications were drawn. `layers.css` says so rather than a number saying
  it in one component.

Spec: [Everything that needs a person](../superpowers/specs/2026-09-06-activity-centre-design.md)

## D115. What needs an answer comes from a list of sources, not a list of ifs

The first section will grow — every capability that can leave something
unresolved wants a line in it. Written as branches inside the panel, that is a
component that imports every feature and is edited by every one of them.

An attention source is a function a feature exports: it returns what is
outstanding, as `AttentionItem`s the panel can draw without knowing what they
are about. `features/activity/sources.ts` lists them, and adding a kind is a
composable in the feature that owns the subject plus a line there. The same
shape the job runner uses for its kinds of work (D81) and the workspace uses
for its panels (D12).

- **The item says what to do about itself.** A label, a tone, a sentence and
  one action — never a branch in the panel on where it came from.
- **An item is dismissible only when dismissing it is honest.** A failed job is
  news and can be waved away; a request for access is not, and comes back until
  it is answered, because the row is still there.
- **A source that cannot answer yet returns nothing.** Not a placeholder — the
  section is empty when nothing is waiting, and an empty section is the goal
  rather than a state to apologise for.

Spec: [Everything that needs a person](../superpowers/specs/2026-09-06-activity-centre-design.md)
