# Minimizing and maximizing floating windows

Date: 2026-09-04. Decision: D92.

## Problem

The common floating-window frame offers only Close. Putting a form aside means
covering it with another window or discarding it, and reading a large form means
resizing its borders manually. The user asked for minimization, maximization and
a footer manager that lasts until page reload.

The legacy `myquasar/src/myapp/components/DraggableWindows/useWindowManager.ts`
and `WindowFrame.vue` were inspected. They retain a rectangle for restoring
maximized windows, but minimizing clears maximization and leaves a title strip.
The rewrite keeps its own component identity and stacking model and puts hidden
windows in the footer instead.

## Interaction and ownership

- Every frame has Minimize, Maximize / Restore size, and Close buttons with
  English accessible labels. Double-clicking the title bar toggles its size.
- A maximized window fills the page above the measured footer, keeping the
  window manager available. Its title bar remains visible; dragging and resize
  handles are disabled until normal size is restored.
- Minimize hides the complete frame without unmounting its contents, closing
  the form, confirming discard or changing its previous size mode.
- The footer adds a row only while windows are minimized. A stable list of
  titles and icons restores individual windows; many entries scroll horizontally
  instead of making the footer taller or squeezing connection commands.
- Restoring or reopening a hidden window reveals the same component and raises
  it. The next visible window is frontmost while another is hidden.
- The manager retains normal geometry independently of maximized display bounds.
  Automatic fitting cannot measure hidden or maximized content into that normal
  rectangle. Browser resizing keeps normal windows reachable and maximized
  windows fitted to the current space.
- The application layout reports a bottom inset; the window engine does not
  inspect connection commands or depend on a workspace feature.
- Closing keeps the existing unsaved-change contract. Window state and the
  footer list are memory-only, with no localStorage or sessionStorage record.

Tab detachment, saved tab groups and operation progress are separate requests
and are outside this change.

## Validation

Write manager tests for visibility, stacking, repeated opens, geometry and
automatic fitting; component coverage for preserving a live form and footer
restoration; and a browser scenario for actual maximized bounds, draft retention
and reload clearing. Tests and other validation commands are deferred at the
user's request until the UX changes are ready for the final validation pass.
