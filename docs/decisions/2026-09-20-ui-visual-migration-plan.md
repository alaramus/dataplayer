# UI visual migration

Date: 2026-09-20.

Target: [the accepted window design](2026-09-13-window-design-and-sizing.md),
applied across the application. Work in small, reviewable portions. Preserve
workflows, source schemas and data contracts. Existing engineering rules may be
refined where the visual migration requires it; do not weaken unrelated checks.

## Sequence

1. Stable connection-window sizing and fixed navigation around a scrolling body.
2. Compact form composition in the shared kit and connection editor: persistent
   labels, shared columns, narrow-container reflow, hints, errors and footer.
   Show the composition in `/ui-kit` in both themes before broad rollout.
3. Neutral chrome and action hierarchy through shared tokens. Inspect existing
   consumers when changing defaults; keep data and status colours meaningful.
4. Migrate complete families of forms: questions, simple forms, tabbed forms,
   variable-content forms. Explicitly choose each window's sizing policy.
5. Align workspace heads, tabs, toolbars, lists, trees, menus and bottom tools.
6. Align grid/editor/viewer surroundings, dashboards and AI; preserve specialised
   content presentation. Finish standalone account, admin and sharing pages.
7. Centralise semantic icon names without changing their appearance first.
   Compare Material Symbols Outlined at real toolbar sizes before switching.

## Design defaults for the next slice

Use the final neutral reference, one prominent primary action, compact desktop
controls and spacing rather than nested decorative cards. Keep meaningful
connection identity colours distinct from neutral chrome. Form, toolbar and
cell contexts are permanent semantic differences, not old/new theme switches.
Derive shared components from actual repeated compositions.

## Durable safeguards

- Keep the short current contract in architecture and live compositions in
  `/ui-kit`; the next contributor should not need historical discussions.
- Extend token ownership and presentation-prop checks where actual bypasses are
  found. Preserve accessibility attributes and dynamic geometry.
- Add deterministic visual scenes with reviewed baselines, alongside behavioural
  assertions by role, text and test ID. Document their distinction from DOM
  snapshots before introducing screenshot comparisons.
- Verify new guardrails with an intentional violation before calling them enforced.
- Keep validation evidence separate from implementation status.

## Slice 1: stable connection geometry

Implemented: explicit stable sizing in the window manager; the connection editor
opts in; name and tabs stay outside its scrolling body; footer actions can wrap.
Other forms retain their current sizing. Viewport shrink constrains stable
rectangles without deriving geometry from the current tab.

Coverage: manager tests for content changes, cascade placement,
resize/maximize/restore and viewport constraints; browser regression for tab
changes, validation, body scrolling, manual resize, maximize/restore and a narrow
viewport.

Validation: all 1,868 frontend unit tests passed; the new Playwright scenario passed;
frontend type-check, lint and production build passed. Lint reported 20 warnings
in unrelated files; the build reported large chunks. The documentation check passed.

Remaining: compact fields and responsive rows are slice 2. This slice does not
claim completion of the full window-design acceptance matrix or visual migration.

## Slice 2: compact connection fields

Implemented: `AppForm` supplies form context to AppInput, AppNumberInput and
AppSelect. `fieldLook` in tokens.ts owns the Quasar appearance mapping; metrics.css
owns control height and label width. Labels stay beside fields in wide forms
and move above them in narrow containers. Schema rows reflow without changing
source metadata. Companion actions remain beside their control. The connection
editor and `/ui-kit` use the composition.

Coverage includes native field names and error associations, typed value updates,
browser alignment and narrow reflow in both themes, and the slice 1 geometry
regression with a deliberately short viewport to exercise overflow.

Validation: all 1,872 frontend unit tests and three targeted Playwright scenarios
passed. Type-check, lint, production build and the documentation check passed.
Lint retains 20 unrelated warnings and the build reports large chunks. Inspected
the generated light and dark form screenshots, including the narrow layout.
The full application E2E suite was not run.

Next: neutral chrome, buttons and tabs, plus presentation of operation results;
then apply the proven composition to the next form family.

## Slice 3: neutral chrome and actions

Implemented: neutral primary/secondary actions through tokens.ts and theme.css;
filled buttons without shadows; neutral chrome and default panel surfaces;
compact field borders and focus; quiet selected tabs in the connection editor.
Keyboard focus remains explicit. Destructive actions, status, data colours and
user-chosen connection colours remain semantic.

Validation: all 1,872 frontend unit tests and four targeted Playwright scenarios
passed. Type-check, lint, production build and the documentation check passed.
Lint retains 20 unrelated warnings and the build reports large chunks. Browser
coverage checks contrast for primary, secondary and both destructive variants in
both themes, neutral action/focus colours, distinct field errors and the existing
connection geometry/reflow scenarios. Inspected the generated light and dark
screenshots. The full application E2E suite was not run.

Next: operation-result composition and the next family of forms. The kit gallery
still contains older card-heavy presentation; migrating compositions remains
separate from these global token defaults.

## Slice 4: connection check results

Implemented: the connection check uses an inline neutral result strip above the
footer instead of a floating card. Long details scroll with keyboard access;
copy, dismiss and recovery actions remain outside that scroll region. The shared
metric bounds its height, and source facts wrap on narrow windows. The existing
connection-specific component still owns the report; extract a shared result
composition when a second consumer establishes its actual contract.

Coverage: component regression for failure details, recovery content, copying
and dismissal; browser scenarios for successful and long failed responses in
both themes and at desktop/narrow sizes. They assert unchanged window geometry,
non-overlapping URL/result/footer regions, keyboard scrolling and visible footer
actions. A real connection-check scenario verifies the same placement.

Validation: all 1,873 frontend unit tests and seven targeted Playwright scenarios
passed, including the existing form reflow and stable-geometry regressions and a
real authentication failure. Type-check, lint, production build and documentation
checks passed. Lint retains 20 unrelated warnings; the build reports large chunks.
Inspected light/desktop success and dark/narrow long-error screenshots. The full
application E2E suite was not run.

Next: apply the compact form composition to a small complete family of forms;
keep window sizing explicit. Other operation-result surfaces remain to migrate.

## Slice 5: SSH key forms

Implemented: creation, import and unlocking use compact fields. AppForm's section
layout owns padding and spacing for standalone forms. AppFileInput participates
in the same label column and retains an accessible native input name, with a
live example in the kit gallery. WindowDialog exposes the existing sizing policy
and a form preset: creation/import are stable; unlocking remains content-sized.
The private-key workflow and server contracts are unchanged.

Coverage: file-field accessibility in the composition unit test; browser scenes
for all three forms in both themes and narrow windows, including conditional
passphrase fields, generation errors, file selection and fixed footer actions.

Validation: all 1,873 frontend unit tests and seven targeted Playwright scenarios
passed, including real key generation/import and the unlock-and-reread workflow.
Type-check, lint, production build and documentation checks passed. Lint retains
20 unrelated warnings; the build reports large chunks. Inspected desktop/light
import and narrow/dark import/unlock screenshots. The full E2E suite was not run.

Next: continue with another complete form family; the preferences page around
these forms and the other operation-result surfaces remain to migrate.

## Slice 6: column property forms

Implemented: column rename, default, type and nullability dialogs use AppForm's
section layout, quiet cancellation and stable compact windows. Long responses
scroll above the footer. Form banners retain semantic status text and icons on
a neutral surface; the mapping remains in tokens.ts and the gallery demonstrates
the composition. Banners outside AppForm keep their existing presentation.

Coverage: form-banner content and recovery-slot regression, browser scenes for
all four dialogs in both themes with long rejected responses, fixed geometry,
body scrolling, narrow widths and visible footer actions.

Validation: all 1,874 frontend unit tests and six targeted Playwright scenarios
passed, including real rename, nullability and type changes and blocked answers.
Type-check, lint, production build and documentation checks passed. Lint retains
20 unrelated warnings; the build reports large chunks. Inspected light rename,
dark type and narrow light default/error screenshots. The full E2E suite was not
run.

Next: addition forms for columns, indexes and constraints; keep source-owned
vocabularies and blocked-operation messages intact during the visual migration.

## Slice 7: structure addition forms

Implemented: add-column, index and constraint forms use the shared compact
composition and stable windows. A compact-form preset fits the shorter forms;
the existing form preset holds the foreign-key options. Form checkboxes align
with fields and use neutral marks through tokens.ts, with a gallery example.
Source-owned choices, method restrictions and mutation payloads are unchanged.

Coverage: checkbox label/state/value and disabled/default behavior; browser
scenes for both themes, multiple selected columns, method restrictions,
foreign-key fields, long errors, narrow reflow and stable geometry.

Validation: all 1,876 frontend unit tests and five targeted Playwright scenarios
passed, including real column/index/constraint creation and blocked answers.
Type-check, lint, production build and documentation checks passed. Lint retains
20 unrelated warnings; the build reports large chunks. Inspected the light index
and dark foreign-key forms, including narrow error/scrolling states. The full
E2E suite was not run.

Next: migrate another complete form family; the structure table and the table
designer remain separate surfaces to review.

## Slice 8: connection and view sharing

Implemented: sharing uses a stable form window with compact link, recipient and
permission fields. Narrow containers place labels above fields; grants and long
link lists scroll above the footer. Companion actions align with compact controls
in AppForm. The browser geometry helper now measures the actual control when an
external label precedes it. Sharing permissions and requests are unchanged.

Coverage: both themes, recipient-load failure and recovery, stable geometry,
companion alignment, narrow reflow and long-list scrolling with visible actions.

Validation: all 1,876 frontend unit tests passed; ten targeted browser scenarios
passed, with one rerun after account creation exceeded its existing five-second
expectation. Type-check, lint and production build passed. Lint retains 20
unrelated warnings; the build reports large chunks. Inspected light desktop and
dark narrow screenshots. The full E2E suite was not run.

Next: dashboard sharing, followed by another small form family. The broader
workspace, table and operation-result surfaces remain to migrate.

## Slice 9: dashboard sharing

Implemented: the dashboard share window uses the same stable form preset,
compact link and recipient fields, aligned companion action and narrow reflow
as connection sharing. Existing grants remain a compact list that scrolls above
the footer. The explanation of access to agents' hosts remains beside the form.

Coverage: browser scenes in both themes measure companion alignment, unchanged
window geometry when grants arrive, narrow overflow and access to the last grant
with the footer visible. Layout fixtures intercept the API without creating data.
The existing real sharing scenario covers granting, editing and revocation.

Validation: all 1,876 frontend unit tests, two layout scenarios and the real
sharing scenario passed. Type-check, lint and build passed; lint retains 20
unrelated warnings and the build reports large chunks. Inspected desktop light
and narrow dark screenshots. The full application E2E suite was not run.

Next: account forms, keeping validation, password handling and account privileges
unchanged. Larger dashboard and workspace surfaces remain separate slices.

## Slice 10: account forms

Implemented: account creation and editing use AppForm's section layout and the
stable compact-form window. Checkboxes align with the controls, and the optional
new-password instruction is a field hint instead of a long label. Validation,
autocomplete policy and mutation payloads are unchanged.

Coverage: both themes, persistent external labels, compact controls, missing
email/password errors without window resizing, narrow reflow, scrollable body
and reachable footer. Editing checks the optional password hint and verifies
that saving an empty password omits it while preserving checkbox choices.
Existing sharing scenarios exercise real account creation and deletion as well
as administrator-only access and the self-deletion restriction.

Next: inspect the remaining small settings and credential forms before moving
to larger workspace surfaces.

Validation: all 1,876 frontend unit tests and five targeted browser scenarios
passed. Type-check, lint and build passed. Lint retains 20 unrelated warnings;
the build reports large chunks. Inspected desktop light editing and narrow dark
validation screenshots. The full application E2E suite was not run.

Follow-up: the 360-pixel compact preset left the edit form permanently
scrollable. The account window now uses a 440-pixel medium-form preset, enough
for its hint and checkboxes at a normal viewport; the browser regression asserts
that its body has no vertical overflow. Narrow viewports still scroll while the
footer stays fixed.

## Slice 11: AI provider key

Implemented: the provider key window uses AppForm's section layout and stays
content-sized, its one field having nothing that appears after opening. The
provider is named by the title instead of a bold line in the body, and a
placeholder that repeated the label is gone; "A key is already set" stays. The
field declares `new-password`, as connection secrets do, so a browser does not
offer the login password for it. Show/hide, check, clear and save behave as
before, and check results remain toasts.

Coverage: both themes; the provider in the title and nowhere else in the body;
the field's accessible name, which the floating label used to merge with the
show/hide button; label beside the field and the action centred on it; unchanged
geometry when the key is revealed; no body overflow; narrow reflow with the
footer in view. The scenario was run against the previous window and failed.

Validation: all 1,876 frontend unit tests, the new layout scenario and the
existing AI scenario passed. Type-check, lint and build passed; lint retains 20
unrelated warnings and the build reports large chunks. Inspected light and dark
screenshots at desktop and narrow widths. The full E2E suite was not run.

Next: the remaining small settings and credential forms, such as service
credentials; the AI tab-attachment window is a checklist rather than labelled
fields and needs its own composition.
