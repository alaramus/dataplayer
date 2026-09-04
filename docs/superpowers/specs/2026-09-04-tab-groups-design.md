# Saved tab groups

Date: 2026-09-04. Decision: D94.

## Interaction

Save tab group asks for a name and captures the current workspace. Each group
gets a header button and an adjacent menu with Update from current layout,
Rename and Delete. The strip scrolls when its buttons exceed the available
header width. Names are trimmed, nonempty, at most 80 characters and unique
within the user's library without regard to case.

Groups are saved copies, not automatically updated workspaces. A person can
save a layout, close its tabs, open other work, and restore the saved layout
later. Update explicitly replaces the group's saved layout; rename changes
only its name, and deleting a group does not close current tabs.

The user specified a warning before replacement with a Don't show again
checkbox remembered in localStorage. The warning appears until accepted with
that box checked. Cancel and the window's close button keep the current layout
and do not remember the checkbox. The preference applies to every group for
that user in this browser. Existing panel close guards remain in force.

## Ownership and restoration

The library is local UI state keyed by the signed-in user. It reuses the
versioned workspace serialization for panel descriptors and the section tree,
including sizes, orientation, active tabs and collapsed states. The feature
checks that required pinned roles and the fixed connections panel remain.
Duplicate identities, invalid geometry and incompatible panel roles are refused.
New section identities use UUIDs so a fresh browser session cannot reuse a
counter value held by a saved group. The legacy application's section defaults
and XFrame layout were inspected; the rewrite keeps its typed section tree.

The engine exposes snapshot and guarded restore. Snapshot applies the same
docking projection as ordinary workspace persistence, so detached tabs are
included without persisting floating frames. Restore validates first, asks all
departing panels before changing the layout, then assigns the complete layout
at once. A refusal or change in the panel set during the guards aborts it.
Panels common to both layouts retain their live instances and editor state.
Unrelated floating forms are not part of a group.

Groups do not freeze data, copy query text, capture transactions or clone
per-table filters, sorting and chart settings. Those remain owned by their
existing features. Restoring a deleted or inaccessible source uses its normal
unavailable/error state; a saved descriptor grants no access.

## Validation status

Write unit coverage for storage, name validation, immutable saved copies,
malformed layouts, guarded replacement and warning preferences. Extend the
component scenario for live panels and detached windows. Write a browser
scenario for save, modify, restore, cancel, remember across reload, multiple
groups and menu actions. Tests, type checks, lint, builds and browser runs
remain deferred until the user's final validation pass.
