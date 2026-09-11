# Detaching a tab into a floating window

Date: 2026-09-04. Decision: D93.

## Interaction

The user clarified that the destination is a floating window inside DataPlayer.
Once a tab drag starts, the application header offers a window outline and
"Drop here to open in a window". Hovering strengthens the highlight; releasing
there detaches the panel. Releasing elsewhere keeps the existing section-drop
rules. Escape, pointer cancellation and browser blur cancel an unfinished drag.
The connections panel, which cannot be closed, cannot be detached either.

A detached panel uses the existing window frame and footer manager. It offers
Return to panel plus the reload and icon actions its tab offered. Its cross
closes the panel through the same guard as a tab cross. Returning does not
close it or ask to discard anything. Opening the same panel again restores and
focuses its window, including when minimized. Several detached panels can
coexist with each other and ordinary form windows.

## Keeping the live view

The old leaf-local KeepAlive would recreate a panel on moving it to another
parent. That loses editor and grid state and can dispose a query transaction.
The workspace instead owns one keyed KeepAlive per open panel. A small target
registry identifies which DOM container currently shows it; Teleport moves the
same content to that target. Panels mount lazily, deactivate when hidden and
unmount on close. Feature injections stay rooted in the workspace page.

The application window host owns only a target and the detached-panel toolbar,
never a second copy of the actual panel. The window follows panel renames and
replacement ids, and disappears when the panel closes, returns, resets or its
workspace unmounts. A floating catalog can be the active connection just as a
docked catalog can.

## Layout and reload

Detach records the origin section, role and tab index and removes only the
layout reference, keeping the panel record. Return first uses that section,
then a section with the same role, then adds a section when none accepts it.
An engine with no remaining section refuses detachment rather than leaving no
place to return; the application always keeps its pinned sources section.

Persistence applies the same return operation to detached panels before writing
the existing version-three layout. Windows remain session-only as in D92, while
their tabs reappear docked after reload. This stores panel metadata only and
does not change where query text or editor drafts live.

The legacy DraggableWindows manager and frame were inspected for window
behaviour. The rewrite reuses its own window manager and immutable panel tree.
Saved tab groups and detachable browser windows are outside this slice.

## Validation status

Write focused tests for detach/return, role fallback, persistence, close guards,
replacement ids and repeated opens. Component tests must retain an unsaved input
and the same mounted instance across section/window targets. A browser scenario
must cover the header preview, drop, minimize/restore and return. Validation
commands remain deferred at the user's request until the final pass.
