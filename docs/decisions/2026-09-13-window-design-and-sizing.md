# Neutral window design and stable sizing

Date: 2026-09-13. Decisions: D131, D132.

Status: agreed design direction; stable sizing is implemented for the connection
editor, which also uses the shared compact field layout. Neutral action styling
and the application-wide migration remain pending.
See the [visual migration plan](2026-09-20-ui-visual-migration-plan.md).

## Visual reference

[Open the connection window example](assets/2026-09-13-window-design/connection-example.html).
The [editable fragment](assets/2026-09-13-window-design/connection-example.fragment.html)
is stored beside it. Both are demonstration assets, not application components.
Inputs and tabs work locally; testing and saving are simulated. The example
does not define supported connector options, validation or backend behavior.
Its height still follows the selected tab: it illustrates appearance only,
not the stable sizing requirement below.

The user's PyCharm Data Sources and Drivers window is the reference for
alignment, restrained borders, compact controls and scrolling within a stable
window. Reproduce those principles, not PyCharm's whole navigation or features.

## D131: visual direction

- Use neutral black and grey surfaces. Avoid a blue tint across backgrounds,
  borders, text and controls. Data, errors and status retain meaningful colors.
- Distinguish the title bar from the form with surface brightness. Keep text
  readable and group hierarchy visible without making everything equally faint.
- Use compact inputs with persistent labels aligned to the left on wide forms.
  Stack labels above inputs when space is insufficient. Align related rows to
  a common label column; keep host and port together where space permits.
- Borders identify inputs and the outer window. Separate major regions such
  as tabs and footer with quiet lines. Avoid nested cards, outlines around every
  group, decorative blue stripes and shadows around internal rounded regions.
- Use spacing and alignment to group fields. The last accepted example replaces
  the earlier card-heavy, blue-tinted proposals; those are not migration targets.
- Give one primary action clear emphasis, secondary actions quieter treatment,
  and destructive actions a distinct semantic appearance. Exact palette values
  and whether a primary action needs a restrained color remain adjustable.
- Keep Quasar underneath the shared UI kit. Centralize colors in `theme.css`,
  geometry in `metrics.css`, appearance variants in the kit and stacking in
  `layers.css`. Features provide content and action meaning, not local palettes.
- Use a common window structure: title, optional tabs/navigation, body, optional
  operation result and footer actions. Simple forms need not acquire tabs.

## D132: sizing and scrolling

Two explicit sizing policies belong to the shared window system:

1. Content-sized: retain the existing behavior for small, simple forms.
2. Stable: use for tabbed forms and windows whose content changes during use.

A stable window opens at a suitable preferred size for its form, with some room
for its fuller tabs, bounded by the available viewport. It must not derive its
ongoing size from the currently active tab. Exact presets and the initial set
of participating windows will be chosen during implementation; this is not a
requirement to measure or mount every tab eagerly.

Switching tabs, loading results, revealing optional fields and showing errors
must not resize or recenter the stable window. A short tab leaves empty space.
Overflow scrolls inside the body; the title, tab navigation and footer actions
remain available. Avoid scrolling the entire window or introducing horizontal
scrolling for ordinary forms; reflow fields as width decreases.

Manual resizing and maximize/restore remain available. A user's selected
rectangle survives tab changes, and maximizing does not overwrite the normal
rectangle. Viewport changes may constrain geometry to keep the window reachable.
Existing minimize, close guards and live form state are preserved. Persistence
of geometry across reopening or browser reload is not part of this agreement.

This selectively replaces D14's continuous content fitting. It does not switch
all windows to a single hard-coded size.

## Implementation and acceptance

Start with the shared frame and connector window as a representative pilot;
identify other variable-content windows explicitly before migrating them.
Do not copy demonstration markup into production or change server contracts
to match example fields. Keep schema-driven forms and existing window controls.

Acceptance scenarios for the implementation:

- Switch repeatedly between short and long tabs: the rectangle remains unchanged.
- Load data or show validation errors after opening: geometry remains unchanged.
- Overflow scrolls while tabs and footer actions stay visible and usable.
- Resize manually, switch tabs, maximize and restore: normal geometry survives.
- Reduce the viewport: the window remains reachable and fields reflow.
- Simple content-sized forms retain their existing behavior.
- Light and dark themes retain readable text, focus and action hierarchy without
  nested decorative borders or tinted background surfaces.

Write meaningful manager/component tests and browser coverage when implementing.
Run checks only with explicit user approval under AGENTS.md. Track implementation
and validation in the migration plan; this specification defines acceptance.
