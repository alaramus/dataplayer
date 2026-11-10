# The welcome and the tour

What a person meets on their first visit: a language and a theme, then a tour
they take with their own hands over the real workspace. Read this before
changing a control the tour points at, a mutation it waits for, or the welcome.

Decisions here: D355.

## What exists today

```
frontend/src/features/onboarding/
├── OnboardingDialog.vue   the welcome: language, theme, take the tour or not
├── tour.ts                chapters, targets and what completes them (pure)
├── basics.ts              the first tour: nine chapters on a SQLite file
├── placement.ts           where the hint stands beside a ring (pure)
├── runner.ts              the running tour: its chapter, what it learned
└── TourHost.vue           the dim, the ring and the hint, over everything
```

Whether the tour was finished or ended is `welcome_tour_done`, a preference of
the account; Preferences starts it again.

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
  its file are deleted by the person as the last chapters; the folder
  connection made on the way stays.

Known deviations:

- **The tour lives in memory.** A reload ends it without marking it done.
- **Only the first tour exists.** The short tours of pipelines, dashboards, the
  agent and services, and the list of them in Preferences, are not written yet.
- **A target is found in the whole document.** A person with another catalog
  open on a table also called `tasks` may see the ring on that one.

Spec: [A tour the person does with their own hands](../decisions/2026-11-10-guided-tour-design.md)
