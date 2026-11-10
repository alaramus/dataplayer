# A tour the person does with their own hands

Decision D355. Replaces the six silent clips of the first-visit welcome.

## What was there

The welcome asked for a language and a theme, then played six recordings:
making a connection, tabs, a table, pipelines, dashboards, the agent. A clip
shows what somebody else did; it does not leave the person with anything they
have done, it goes stale with every change to a screen, and six of them in a
row are skipped by most people halfway.

## What replaces it

The welcome keeps the language and the theme, then offers two buttons: take
the tour, or look around alone. Either one closes the window; the tour runs
over the workspace itself.

A step points at one control: the rest of the screen is dimmed, the control is
ringed, and a short hint stands beside it. The step ends when the person has
done the thing — not when they press Next. Nothing is blocked: the dim does
not take clicks, so somebody who wanders off can come back to the ring.

### The scenario

Nine chapters on one SQLite database made for the purpose, about three
minutes, ending with nothing of the demonstration left behind:

1. **Make a database.** New connection, SQLite, *Create here*: the lab of D261
   in the person's own storage, with no server to start (D263).
2. **Open a table** — `tasks`, which has a status and a priority worth filtering.
3. **Filter it** — blocked tasks only.
4. **Change a cell.**
5. **Run a query** — the table opened as a query, then Run.
6. **Delete the connection.** The file stays in the person's storage: a
   connection is a way to a source, not the source.
7. **Connect your own folder** — a file connection to the personal storage.
8. **Find the database file** in it.
9. **Delete the file.**

The folder connection of chapter 7 stays: it is the person's storage, not a
demonstration, and the obvious place for their next upload.

Dragging tabs was in the first draft and left: dragging along a hint is
awkward, and the console of chapter 5 shows tabs anyway.

### Everything else: short tours later

Pipelines, dashboards, the agent, starting a service, a table as a graph or
as documents are not chapters of this tour. Each will be a tour of three to
five steps of its own, offered from a list in Preferences and when somebody
opens that part of the application for the first time. A long tour is
abandoned in the middle; a short one met when it is wanted is not.

## How a step finds its control

By `data-testid`, the name the Playwright scenarios already use. A second set
of names for the same controls would drift from the first; the tour's own
scenario fails when a control it points at is renamed.

A chapter is an ordered list of targets and one condition of completion. The
ring is on the furthest target that is visible and ready: New connection,
then the SQLite card once the catalog is open, then *Create here* once SQLite
is chosen. Closing a window halfway moves the ring back by itself, so there is
no state of "the person went the wrong way" to recover from.

A chapter is complete when the operation it is about succeeded, which the tour
learns from vue-query's mutation cache: the few mutations it waits for carry a
`mutationKey`, and the tour reads the variables and the answer of a successful
one. Features import nothing of the tour. Where no mutation marks the moment
— a filter is query state — the condition is a control the screen shows only
afterwards, such as the count on the Filters button.

What one chapter learns the next one needs: the connection that was made, the
file it is in, the folder connection. The tour keeps them while it runs.

## Rejected

- **A library** (driver.js, Shepherd, Intro.js). Their overlays bring their own
  layers and colours, which this application states in `layers.css` and
  `theme.css`; Shepherd and Intro.js are AGPL or commercial. What is needed is
  a ring, a card and a loop that reads rectangles.
- **Signals sent from each feature.** Every screen the tour passes would import
  it; a mutation key is a property of the request and stays true when the
  tour is gone.
- **A managed PostgreSQL as the demonstration.** The most visual thing the
  application does, but it waits for a pull and needs a container runtime.
  It becomes one of the short tours.
- **Resuming after a reload.** The tour is in memory. A reload ends it without
  marking it done, so the welcome opens again and the tour starts over, with a
  new numbered file beside the first.
