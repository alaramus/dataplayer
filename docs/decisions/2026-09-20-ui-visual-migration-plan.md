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

## Slice 12: service address

Implemented: the window saying where a service answers uses AppForm's section
layout in a stable `form` window, so the answer arriving after it opens no
longer grows it from a spinner to its full height. Host, port, user, database,
password and URL are read-only fields with their copy action beside them, as
the sharing link is. AppInput gains `monospace`, shown in the kit gallery: the
old rows set values as code, and the reference sets the URL that way. The
password notes are form banners. What is shown, when a password is included and
the server's URL are unchanged.

Coverage: a layout scene with a delayed answer in both themes: unchanged window
geometry, labels beside read-only monospace fields, the copy action centred on
the URL, no body overflow on desktop, narrow reflow and scrolling with the
footer in view. Run against the previous window it failed on the values, and
with content sizing on the geometry. The services scenarios read the values as
field values, and the check that a listed address carries no password now reads
the fields as well as the text.

Validation: all 1,876 frontend unit tests passed; the new scene, the three real
services scenarios (PostgreSQL, SSH with a password, SSH with a key) and the
kit gallery and connection form scenes passed. Type-check, lint and build
passed; lint retains 20 unrelated warnings and the build reports large chunks.
Inspected both themes at desktop and narrow widths, and the password-revealing
window of real PostgreSQL and SSH services. The full E2E suite was not run.

Next: the start-service form, then backups; the AI tab-attachment window is a
checklist rather than labelled fields and needs its own composition.

## Slice 13: starting a service

Implemented: the start-service form uses AppForm's section layout in a stable
window instead of a 900-pixel content-sized one that grew by 450 pixels when
"Let me choose" revealed its fields. The longest variant, an SSH server signed
into with a key, is seven rows, two hints and a paragraph whose image name
takes three lines; it overflowed `form` by four pixels, so WindowDialog gains
`long-form`, 560 by 620. Labels shortened to fit the label column: "Name",
"User" and "Database" with an "Optional" placeholder, and "Port" with "On this
machine" moved into its hint. The name, user and database fields say `off` and
the password `new-password`, so a browser does not read the form as a sign-in.
Choices, validation and the request are unchanged.

Coverage: both themes; unchanged geometry between modes and with a rejected
password; labels beside fields, compact heights, the sample-data checkbox on
the control column; no body overflow for PostgreSQL and for an SSH server with
a key; narrow reflow with the footer in view. Run against the previous form it
failed on the geometry. Nothing is started by the scene.

Validation: all 1,876 frontend unit tests passed; the new scene, the three real
services scenarios, which fill this form, and the service address scene passed.
Type-check, lint and build passed; lint retains 20 unrelated warnings and the
build reports large chunks. Inspected light and dark desktop, a narrow dark
form and the SSH key variant. The full E2E suite was not run.

Next: backups, then the remaining grid forms (download, import, create table);
the AI tab-attachment window needs a checklist composition of its own.

## Slice 14: backups

Implemented: the backups window is a stable `medium-form` window instead of a
content-sized one that grew with the list up to the viewport. "Copy this
database out" moved from a full-width button at the top of the body into the
footer as its primary action, beside a new Close. Files are a flat list on the
window's surface, separated by faint lines, rather than raised rows; availability
warnings are form banners. Restore, delete, their confirmations and the jobs
they start are unchanged.

Coverage: the first browser scene for this window, with the availability answer
and the list held until the window is open: unchanged geometry when they
arrive, the primary action in the footer, rows without a surface of their own,
no horizontal overflow, the last row reachable by scrolling with the footer in
view, a narrow window, and an unavailable server disabling copying and
restoring while deleting stays offered. Run against the previous window it
failed on the geometry. Nothing is copied, restored or deleted.

Validation: all 1,876 frontend unit tests passed; the new scene and the actions
scenarios, which reach this window's menu line, passed. Type-check, lint and
build passed; lint retains 20 unrelated warnings and the build reports large
chunks. Inspected both themes at desktop and narrow widths and the unavailable
state. The full E2E suite was not run.

Next: the grid forms — download, import and create table.

## Slice 15: downloading rows

Implemented: the download window chooses between the current page and every
matching row with a new kit component, AppRadioGroup, instead of two bordered
boxes whose chosen button was filled like a second primary action beside
Download. Each option keeps its line: the page's range and columns, the filters
and streaming, or the reason a source cannot export every row. In a form the
group's label takes the label column and its marks are neutral through
tokens.ts; ESLint forbids `q-radio` and `q-option-group` outside the kit,
verified by adding both spellings to a screen; the gallery shows it inside the
form composition and on its own. Cancel is quiet. The window stays
content-sized: nothing appears in it after opening. What is downloaded and
where it goes are unchanged.

Coverage: the component's names, descriptions, emitted values, disabled and
repeated choices and its form and standalone looks; the download unit test now
checks that an unavailable scope cannot be chosen rather than reading a button's
`disabled`. A browser scene in both themes checks the group's name and the
options' descriptions, the label on the first option's line, unchanged geometry
when the scope changes, no overflow and narrow reflow. Run against the previous
window it failed.

Validation: all 1,881 frontend unit tests passed; the new scene, the grid
scenarios including a real export, and the kit gallery scene passed.
Type-check, lint and build passed; lint retains 20 unrelated warnings and the
build reports large chunks. Inspected both themes at desktop and narrow widths
and the gallery's composition. The full E2E suite was not run.

Next: loading a file into a relation (import), then creating a table.

Follow-up: with "Rows" as the window's only label, the 108-pixel label column
read as a gap between it and the choices. A radio group without a label now
spans the form and is named by `aria-label`; the download window uses that, so
its choices start where the subtitle does. The scene asserts that alignment and
waits for the mark of the choice left behind to finish shrinking before its
screenshot. All 1,882 unit tests, the scene, the grid scenarios and the kit
gallery scene passed, except "keeps the 500-row page mode interactive", which
timed out in the batch and passed alone twice at 29 to 30 seconds against its
30-second limit — a pre-existing margin, not this change.

## Slice 16: picking another source

Implemented: bringing rows in and declaring a reference share NodePicker, so
both moved together. The import window was a 900-pixel content-sized window
that grew from 229 to 616 pixels and climbed the screen as a source was picked,
walked, paired and previewed; it is now stable at the new `wide-form` preset,
900 by 600. Declaring a reference takes a stable `form`. The picker's source is
a compact field, and its trail and list stand in the control column under it
through a new kit component, AppFormControl, shown in the gallery; the list's
entries start at the left. The pairs of columns are on the window's surface
instead of a bordered card, the preview is headed like them, a narrow form keeps
the pairs side by side without the arrow, and Cancel is quiet. What is read,
paired, previewed, brought in or declared is unchanged.

The architecture file's list of every migrated window, which AGENTS.md asks not
to keep and which was nearing the size warning, gave way to the rules it
illustrated: when a window is stable and which preset, short labels, read-only
values, AppFormControl and flat lists. This plan remains the record of which
window took what.

Coverage: a scene in both themes with two real connections: unchanged geometry
from opening through choosing a source, walking to a table, pairing and a
preview; the walk in the control column; pairs without a card; no horizontal
overflow and a reachable footer at a narrow width; and the declare window's
labels in one column and unchanged size once the far column appears. Nothing is
brought in or declared. Run against the previous windows it failed.

Validation: all 1,885 frontend unit tests passed; the new scene, both real
import scenarios, the declared-reference scenario and the kit gallery scene
passed. Type-check, lint and build passed; lint retains 20 unrelated warnings
and the build reports large chunks. Inspected both themes, the walk, the preview
and a narrow import, and the declare form. The full E2E suite was not run.

Next: creating a table from a file, which pairs columns the same way.

## Slice 17: creating a table

Implemented: creating a table from a file and from rows use AppForm's section
layout in stable `wide-form` windows instead of content-sized 900-pixel ones.
Their destinations are rows in the label column rather than three floating
fields abreast; "CSV or TSV file" became "File" with the formats in its hint,
and the warning about a new schema is that field's hint instead of a banner.

The third copy of the column-pairing layout was the signal to extract it:
AppPairs and AppPairsRow in the kit now hold the legend, the arrow, the
separators, the quiet pair and the narrow reflow for bringing rows in and both
ways of creating a table. The copies had drifted — a count in the legend's own
grid column pushed the headings 12 to 28 pixels off the fields under them — and
creating from rows still labelled "New column" and "Type" on every row; its
type is now a legend column. A form's switches are on in the neutral a form's
checkbox is ticked in, through tokens.ts. The gallery shows AppPairs with all
its slots. What is read, named, typed and created is unchanged.

Coverage: component tests for the legend, the arrow's direction, quiet pairs,
the third column and the switch's colour in and out of a form. A browser scene
in both themes opens both windows on a real connection: geometry unchanged
while a file is read, a new schema is chosen, a destination answers and a pair
is left out; each heading over its column's fields; no overflow at a narrow
width. Nothing is created. Run against the previous windows it failed on the
heading alignment.

Validation: all 1,893 frontend unit tests passed; the new scene, the actions
scenarios including loading a CSV, both real import scenarios, the source
picker scene and the kit gallery scene passed. Type-check, lint and build
passed; lint retains 20 unrelated warnings and the build reports large chunks.
Inspected both themes, a narrow window and both windows' pairs. The full E2E
suite was not run.

Next: the remaining catalog and grid windows — cell value and cell editor, the
model code window and the action dialog — then the AI tab-attachment checklist.

## Slice 18: cell value and editor windows

Implemented: the full-cell viewer is a stable 900 by 360 window whose plain
preformatted value scrolls with the body, without a nested card or a second
scroll ceiling. The cell editor uses AppForm's section layout in a stable
`compact-form` window; its nullable switch aligns with the value field, a
refusal is a form banner and Cancel is quiet. Copying, typing, SQL NULL and
saving are unchanged.

Coverage: a browser scene in both themes opens both windows on a real relation,
checks the viewer's content and copy action, compact label alignment, unchanged
editor geometry when a rejected save appears, narrow reflow, no horizontal
overflow and reachable footer actions. The existing real scenarios still open
the full JSON value and update a cell through values and SQL NULL.

Validation: all 1,893 frontend unit tests and four targeted browser scenarios
passed. Type-check, lint and build passed; lint retains 20 unrelated warnings
and the build reports large chunks. Inspected both themes at desktop and narrow
widths. The full application E2E suite was not run.

Next: the model code window, then the action dialog and the AI tab-attachment
checklist.

## Slice 19: model code window

Implemented: the model-code workflow uses a stable `wide-form` window across
loading, a written document and a refused dialect. The dialects are an
accessible one-line tab list, while the editor fills the remaining body and
owns its scrolling. The fixed footer follows the shared hierarchy: the
external-site door and Close are quiet, Copy is secondary, and Save is the
primary last action. Writing, copying, saving and opening the drawing site are
unchanged.

Coverage: a browser scene in both themes holds the first response to observe
loading, then moves through a document, a refused dialect and another document
without changing window geometry. It checks the chosen-tab semantics, disabled
Save on refusal, no horizontal overflow and reachable footer actions at a
narrow width. The existing real model-code scenario still writes and downloads
the model.

Validation: all 1,893 frontend unit tests and three targeted browser scenarios
passed. Type-check, lint and build passed; lint retains 20 unrelated warnings
and the build reports large chunks. Inspected both themes at desktop and narrow
widths. The full application E2E suite was not run.

Next: the action dialog, then the AI tab-attachment checklist.

## Slice 20: generic action window

Implemented: the generic action dialog is a stable `medium-form` window and its
body is an AppForm section. Schema fields therefore use the same label column,
control geometry and narrow reflow as every migrated form. Destructive
questions, staged files, refusals and previews change inside the scrolling body
without moving the window or its fixed actions. Running actions, previews,
uploads and conflict answers are unchanged.

Coverage: a component test fixes the stable preset and shared-form boundary. A
browser scene in both themes stages several files, removes one and checks that
the window does not move; it also checks narrow-width overflow and reachable
footer actions. Existing action scenarios cover previews, destructive actions,
uploads, conflicts and ordinary fields.

Validation: all 1,894 frontend unit tests and 13 browser scenarios passed.
Type-check, lint and build passed; lint retains 20 unrelated warnings and the
build reports large chunks. Inspected both themes at desktop and narrow widths.
The full application E2E suite was not run.

Next: the AI tab-attachment checklist.

## Slice 21: action height correction

Implemented: the generic action window no longer assigns a medium stable
rectangle to every command. Ordinary actions such as creating, renaming,
moving, archiving, extracting, deleting and setting expiry now fit their
content. Actions whose source preview can arrive or change keep a stable
`compact-form`; actions staging a file list keep the stable `medium-form`.
The rule reads capabilities from the action contract and contains no list of
action names.

Coverage: the component test covers all three policies. Browser scenes in both
themes check a content-sized New folder form, a compact stable destructive
preview and a medium stable upload list, including narrow-width overflow and
reachable actions.

Validation: all 1,894 frontend unit tests and 15 browser scenarios passed.
Type-check, lint and build passed; lint retains 20 unrelated warnings and the
build reports large chunks. Inspected simple, preview and file-list forms in
both themes and at narrow width. The full application E2E suite was not run.

Next: the AI tab-attachment checklist.

## Slice 22: AI workspace-tab attachments

Implemented: the attachment window is a compact checklist with the same inset
and footer rhythm as the other content-sized windows. Every choice now names
the connection, node and panel kind required by D133, while a catalog does not
repeat its connection name. Long choices wrap inside the window; selected
tabs become removable, single-line chips that truncate before they can widen
the composer.

Coverage: the context unit tests fix the complete labels. A browser scene opens
a real catalog and rows tab, selects both through the plus menu, checks the
labels and removal, and verifies that the window and composer have no
horizontal overflow at 420 px.

Validation: all 1,895 frontend unit tests and the targeted browser scene
passed. Type-check, lint and build passed; lint retains 20 unrelated warnings
and the build reports large chunks. The window and selected chips were
inspected in both themes at 420 px. The full application E2E suite was not run.

## Slice 23: table designer

Implemented: the main Create table object editor is a stable `xl` window. Its
system title is no longer repeated by a second document bar. Definition and
SQL review scroll inside the body, while status and the Review SQL or Create
table command stay in the shared fixed footer. Changing sections, showing a
planning problem and moving to review no longer changes the window geometry.

Coverage: the real table-design browser scenario checks the single title,
stable geometry through a planning problem and review, no horizontal overflow
at 600 px, a non-scrolling window content frame, and a footer command that
remains in the viewport. It still creates the designed table through the SQL
review; the close guard still discards a separate draft.

Validation: all 1,895 frontend unit tests and both table-design browser
scenarios passed. Type-check, lint and build passed; lint retains 20 unrelated
warnings and the build reports large chunks. The definition and review steps
were inspected in both themes at the constrained size. The full application
E2E suite was not run.

Follow-up: the editor's geometry had moved but its controls still used their
standalone Quasar look. The destination strip and every object inspector now
live in AppForm: text and select controls receive the shared outlined field
surface, border, height and radius, while checked controls receive the neutral
form colour through tokens.ts. At 850 px the three destination fields become
rows before their controls are squeezed away. The browser scenario asserts
that every visible field is outlined and a selected checkbox carries the
semantic form token. All 1,895 unit tests, both table-design browser scenarios,
type-check, lint and build passed; one unrelated DataGrid unit test first
reached its five-second timeout, then passed alone and in the repeated full
suite.

Follow-up after visual review: an ordinary form's side label column did not fit
the designer's multi-column rows: Schema lost its value and Order and Nulls
collapsed to slivers. AppForm now has a `grid` composition for structured
editors: it keeps the tokenized outlined controls and neutral selections but
places each label directly above its control. The designer uses it throughout,
starts with `new table`, stacks its destination fields before they become
crowded, and uses the neutral active surface in its object navigation. Browser
coverage fixes the default name and schema, field look, index-row containment
and usable widths for Order and Nulls.
