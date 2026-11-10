# The welcome and the tour

What a person meets on their first visit: a language and a theme, then a tour
they take with their own hands over the real workspace; and the short tours
of the rest, taken from Preferences. Read this before changing a control a
tour points at, a mutation it waits for, or the welcome.

Decisions here: D355, D356.

## What exists today

```
frontend/src/features/onboarding/
├── OnboardingDialog.vue   the welcome: language, theme, take the tour or not
├── tour.ts                chapters, targets and what completes them (pure)
├── basics.ts              the first tour: ten chapters, a SQLite file to Redis
├── shortTours.ts          the table read other ways, a pipeline, dashboards, the agent
├── kit.ts                 what a short tour makes and takes away itself
├── done.ts                which tours the account has taken
├── placement.ts           where the hint stands beside a ring (pure)
├── runner.ts              the running tour: its chapter, what it learned
└── TourHost.vue           the dim, the ring and the hint, over everything
```

Whether the welcome's tour was finished or ended is `welcome_tour_done`, the
short ones taken are `tours_done`, both preferences of the account. Every tour
is a row of Preferences → Tours (`features/preferences/ToursSection.vue`).

## D355. The tour is done by hand, chapter by chapter

The welcome plays no clip. A chapter rings one control at a time and is
complete when what it asks has happened.

- **A target is a `data-testid`.** The names the Playwright scenarios hold on
  to; renaming one breaks `tests/onboarding.spec.ts`, which walks the tour.
- **The ring is on the furthest target that is visible and ready.** Targets are
  listed in the order a person reaches them, so closing a window halfway moves
  the ring back by itself; a target may add a condition, such as a tick box
  being ticked before Actions is pointed at.
- **A chapter is completed by a successful mutation or by a control that
  appears.** Mutations the tour waits for carry a `mutationKey` exported from
  their feature's `api.ts`; the tour reads the mutation cache, and no feature
  imports the tour.
- **Nothing is blocked.** The dim takes no clicks and the ring is drawn around
  the control, under Quasar's menus and dialogs (`--dp-layer-tour`), so a
  menu item or a confirmation opened from a ringed control stays usable.
- **The demonstration cleans up after itself.** The SQLite connection and then
  its file are deleted by the person; the folder connection made on the way
  stays.
- **It ends on a server that could be started here.** The last chapter rings
  Redis's Start in the catalog of types and starts nothing; Next ends the tour
  with that window open, for the person to go on alone. A chapter that only
  shows is completed by the hint's Next, offered on its last target, on one
  marked `enough`, or when none of its targets is on screen.

Known deviations:

- **The tour lives in memory.** A reload ends it without marking it done.
- **A target is found in the whole document.** A person with another catalog
  open on a table also called `tasks` may see the ring on that one.

Spec: [A tour the person does with their own hands](../decisions/2026-11-10-guided-tour-design.md)

## D356. The rest is short tours, and a practice database is made and taken away

Four tours of four to six chapters, each a row of Preferences → Tours:

- **A table, read other ways** — chart, structure, documents — and **a
  pipeline** — the practice table saved as a CSV in the person's folder, then
  seen in Data — are done by hand on a SQLite file the tour makes before its
  first chapter (`setup`) and deletes, file and all, when it ends however it
  ends (`cleanup`). The pipeline's folder connection is made only where the
  person has none; it and the pipeline's CSV stay. The pipeline goes with the
  database its card reads.
- **Dashboards** and **the agent** only show where things are: the store or
  New dashboard, an agent's registration and the connections' switch; the key
  beside the default model, a chat's model, what is attached. Nothing is
  started and no data is waited for — an agent reports from elsewhere.
- **A taken tour stays offered**, as Again; `tours_done` is added to one tour
  at a time (`tour_done` in the update), so two tabs cannot undo each other.
- **A connection is deleted with its file on request**: `DELETE
  /connectors/{id}?with_file=true` asks the type through `MakesSourceHere`
  for the file of the owner's storage it holds and removes it with what
  SQLite keeps beside it, before the connection. Another of the owner's
  connections on the same file refuses it (`connectors.file_shared`); a type
  that holds none answers `connectors.no_file_to_remove`.
- **A practice connection gets a name of its own** (`practice`, `practice-2`,
  …), because chapters find it by name and one left from an earlier run must
  not be the one ringed.

Known deviations:

- **The pipeline's last chapter rings the first `tasks…csv`.** A folder
  holding copies from earlier runs may show an older one; the name a run gave
  its file is not known to the screen when the chapter begins.
- **Not offered on first opening a part.** Only Preferences starts a short
  tour.

Spec: [The short tours](../decisions/2026-11-10-short-tours-design.md)
