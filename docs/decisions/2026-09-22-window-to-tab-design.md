# A window whose contents can live as a workspace tab

Date: 2026-09-22. Decision: D155.

Status: implemented with this specification.

## What was asked

Some windows hold something a person wants to keep while working, not a form
being filled in: a widget detached from its dashboard, the output of a service
that failed to start. A floating window covers the columns and joins the
taskbar; a workspace tab sits in the column of work, survives a reload with the
layout and is split and dragged like any other. The user asked that such a
window may be turned into a tab of the workspace.

## Options

1. **A "dock" command in the window engine.** The engine knows nothing about
   what a window holds — that is the split D14 keeps — so it cannot say which
   panel the window's contents would make. A generic dock would have to be
   taught each feature's identity rules, which is the knowledge the split
   exists to keep out.
2. **A window action the feature supplies.** A window already declares
   commands of its own in its bar (D112): the engine draws an icon and calls
   what it is given, and the feature knows both how its contents become a
   panel and which window to close behind it.
3. **Replacing the windows with panels outright.** The window is the right
   first step: a widget is detached to watch it over the data, and only some
   of those deserve a lasting tab. Making every detach a tab would fill the
   strip with what was meant to float.

The second was chosen.

## Decision

- A window whose contents can live as a workspace tab says so with one preset,
  `openAsTabAction` in `shared/windows`, placed in the window's `actions` slot.
  The preset holds the icon, the words and the test id; the feature's `run`
  opens the panel through the workspace and closes the window — a move, not a
  copy. `WindowDialog` takes the same `actions` prop so a dialog declares it
  the way a hand-built window does.
- Two new panel kinds hold what moves. `widget` carries the whole widget, the
  range and the interval of the moment the window was opened, and the
  dashboard's id: the tab follows the window's snapshot semantics, so a widget
  changed or removed on the dashboard does not reach it, and the widget is
  validated by the panel schema on the way back from storage like everything
  else the layout holds. `service-logs` carries the service's id and name, and
  reads the output again whenever the tab is shown.
- The identities differ by meaning. A service's output has one answer, so the
  tab is `service-logs:<serviceId>` and asking for it again brings the tab
  that is there forward. A widget window is already a copy, and two copies are
  two tabs, so the tab's id is
  `widget-tab:<dashboardId>:<widgetId>:<fresh suffix>`.
- The first participants are the dashboard widget window and the service
  output dialog. The dialog shows the command only where a workspace is
  provided to receive the tab; elsewhere the command is absent rather than
  inert.

## Consequences

- The window engine changed not at all: the preset is one more caller of the
  `actions` slot D112 added.
- A widget tab restores from a stored layout with its snapshot intact, because
  the copy is data on the panel rather than a message to it.

## What this does not try

- No general "any window into a tab": a window declares the command, and a
  form never does.
- The tab does not follow the dashboard afterwards; that is the window's
  semantics, kept on purpose.
