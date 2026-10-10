# Connection window: floating windows and form layout

Date: 2026-08-23
Status: agreed
Subproject: 7-preparation

## Goal

Today a connection is edited in a modal dialog: one at a time, fields in a flat
column, the type as a line, buttons at the bottom. The reference is the "Data
Sources and Drivers" window in PyCharm: Host and Port in one row, tabs, the
connection string at the bottom, `Test Connection` to the left of
`OK / Cancel / Apply`.

But the main requirement is not about appearance. **There must be several
windows at once**, so that an existing connection can be kept open and values
copied from it into a new one next to it, without going back and forth. A modal
window forbids this by definition: it blocks everything until it is closed.

The catalog of source types stays what it is, and stays modal. The window is
opened from it and from the list of connections.

## What we carry over from the old application

`myquasar/src/myapp/components/DraggableWindows/` — a floating window engine,
239 lines of manager and 520 lines of frame. We take the idea, not the
construction:

| there | here | why |
| --- | --- | --- |
| `zIndexCounter = ++` without limit | order in a list | nothing to count and nothing to overflow |
| geometry edited in place inside the manager | pure functions, the result is assigned | otherwise nothing can be checked without mounting |
| no bounds at all | clamping on every change | a window beyond the screen edge could not be brought back |
| `openWindow({component})` | a registry by window kind | `panels.ts` already fixed the same mistake |

From `EditConnectorModal.vue` (1384 lines) we carry over nothing. Its
`isFieldShowing` is ninety lines of maps like `{user_password: true,
no_auth: false}`, a map per field name, on the client. The set of fields is
declared by the server, and that is the next subproject.

## Decisions

### O1. Working windows are not modal, and this is not a caveat

Several windows on top of the workspace, blocking neither it nor each other.
That is the requirement: one window is read, the other is typed into. After the
first implementation the same host became shared by the catalog's action forms,
viewing and editing a cell, inserting a row, adding a column and questions about
irreversible actions. The type catalog for **New connection** stays modal: it is
a choice before work starts, not work next to the workspace.

The cost is named at once: modality is what keeps the user from leaving an
unfinished form, and it is gone. So closing a window with unsaved edits asks
(O7) rather than silently throwing them away.

### O2. A window is identified by what it shows

`connector:<id>` for an existing connection, `connector:new:<n>` for a new one.
Calling the same connection again brings the already open window forward
instead of creating a second one.

Not for tidiness. Two windows of one row are two different unsaved edits of the
same thing, and whichever is saved second silently overwrites the first. New
windows, meanwhile, can be as many as you like: a draft has no row that can be
overwritten.

The same technique as `catalogPanelId` / `rowsPanelId` in `panels.ts`.

### O3. Geometry is pure functions

`shared/windows/geometry.ts`: cascade placement, clamping to bounds, bringing
forward, autosize and resize from every edge. No components, no requests — checked without mounting, like
`tree.ts`, `placement.ts` and `adapterSearch.ts`.

The split is the same as in the workspace: `shared/windows` does not know what
a connection is, and `features/connectors` does not know how a window moves.

### O4. A window cannot be lost

Every geometry change is clamped so that the title bar stays inside the browser
window — not the whole window, otherwise it could not be moved partly past the
edge, but exactly the bar it is dragged by. When the browser is resized,
clamping is repeated for all windows.

The old engine had no clamping, and a window dragged past the right edge
disappeared for good: there was nothing to bring it back with.

### O5. A cascade, not a stack

A new window is offset from the previous one by a constant step. Windows laid
exactly on top of each other contradict the reason all this was started — to see
two at once.

The offset is computed from the **last opened**, not from the number of open
ones: otherwise closing a middle window shifts the next one back onto an
occupied spot.

### O6. The server lays out the form

`FieldSpec` gets two fields: `group` — the tab, `row` — the row. Both arrive
from the JSON Schema, where they come from the options model:

```python
host: str = Field(title="Host", json_schema_extra={"row": "address"})
port: int = Field(default=5432, title="Port", json_schema_extra={"row": "address"})
```

The client does not guess from the field type that a number is narrow and will
stand alongside. The rule that an address is a host with a port belongs to
whoever declares the address.

A tab is declared the same way. While `general` is enough for both types, the
tab strip is not drawn — one tab is not a choice — but the mechanism is in
place, and SSH/SSL in the next subproject will not require editing the screen.

### O7. OK / Cancel / Apply

- **Apply** — save and keep the window. For a new connection — create, and the
  window **becomes the window of that connection** (`connector:new:1` → `connector:<id>`).
  Otherwise a second Apply would create a duplicate.
- **OK** — the same and close.
- **Cancel** — discard and close.
- Closing with the cross when there are unsaved edits asks. There is no
  modality any more, so this is the only thing standing between an edit and an
  accidental click elsewhere.

### O8. The server assembles the connection string, and it is only shown

A new capability protocol:

```python
@runtime_checkable
class SupportsConnectionString(Protocol):
    def connection_string(self) -> str: ...
```

and a route `POST /connectors/describe-draft`, which builds an adapter from the
form values and asks it for the string. No connection is opened.

Three consequences, and all three are arguments for exactly this construction:

- **A file source has no connection string.** It does not satisfy the protocol,
  the route answers 501, and no string appears in the window. This is the same
  technique by which a missing `fetch` or `catalog` answers 501 — the source
  itself says what it does not have.
- **The password does not get into the string.** It is assembled by the same
  layer that is already obliged to keep the password out of error text; on the
  client this would be a second place where this has to be remembered.
- **The DSN assembly rule lives in one place.** A template in the schema and
  substitution on the client would be cheaper — no request while typing — but
  that is exactly "the same computation in two places", which ENGINEERING.md
  calls a defect.

The price is named: a request while typing. It is softened by a delay and by
the request being sent only when the values pass the schema.

### O9. Test Connection at the bottom left

Where it is in the reference, and next to what the last check said. It feeds
the same dot in the list of connections as before: one check, one record.

## What changes

### Backend

```
app/adapters/
├── protocol.py           + SupportsConnectionString
├── postgres/
│   ├── options.py        + row/group on fields
│   └── session.py        + connection_string(), without the password
│       adapter.py        + facade method
└── file/options.py       + group on the field
app/connectors/routes.py  + POST /describe-draft
```

### Frontend

```
frontend/src/
├── shared/
│   ├── windows/            new: floating window engine
│   │   ├── geometry.ts     pure: cascade, clamping, size, bringing forward
│   │   ├── model.ts        WindowState, WindowLook
│   │   ├── useWindows.ts   state and actions
│   │   ├── context.ts      what components see
│   │   ├── WindowFrame.vue frame: title, dragging, cross
│   │   ├── WindowHost.vue  all windows at once
│   │   ├── WindowDialog.vue a managed form inside the shared host
│   │   ├── presets.ts      identical questions and deletions
│   │   └── index.ts
│   └── SchemaForm/
│       ├── jsonSchema.ts   FieldSpec + group, row
│       └── SchemaFields.vue layout by rows
└── features/connectors/
    ├── ConnectorWindow.vue new: window content
    └── windows.ts          which connection windows exist
```

`ConnectorDialog.vue` goes away: what it did, the window now does.

## What holds it

| Check | What it catches |
| --- | --- |
| `pytest tests/adapters/test_postgres.py` | the connection string is assembled and contains no password |
| `pytest tests/connectors/test_describe_routes.py` | 501 for a source without the capability; 422 for invalid values |
| `bun run test:unit` | `geometry.ts`: cascade, clamping, autosize, resize at each edge, bringing forward |
| `bun run test:unit` | `jsonSchema.ts`: fields of one row are gathered together, order is kept |
| `bunx playwright test` | two windows at once, dragging and resize, calling again brings forward, Apply does not create a duplicate |

What a unit test will not prove is checked separately: that two windows are
really visible at once and do not cover each other completely — by comparing
rectangles in the browser.

## Known deviations this adds

- **Windows do not survive a reload.** The workspace layout does, windows do
  not: a half-filled form restored without secrets would promise more than it
  holds.
- **The connection string is a request while typing.** With a delay and without
  a connection, but still a request on every meaningful change of the form.
- **The tab strip is not visible.** The mechanism exists, there is only one
  group so far, so there are no tabs on screen — that is, this half of O6 is not
  verified in the browser.
- **Nothing minimizes or maximizes.** The old engine had `minimize` and
  `maximize`; they are absent here, because a window is a one-off action, not a
  place to live in.
- **Window positions are not remembered between showings.** A window closed and
  opened again lands by the cascade, not where it stood.

## Edits after the first showing

Everything below follows remarks made after the window was seen in use. The
decisions of this spec are not cancelled, but three of them are changed;
recorded here, not only in code.

- **The "Driver: PostgreSQL" line is removed.** By O9 the form "names the type
  rather than offering to choose it". It still names the type — with a new
  connection that opens already named after the type ("PostgreSQL") — and a
  separate line with one driver per type would only repeat the icon in the
  window title. It will have to come back when one type gets several drivers.
- **The check result is a panel above the button, not a line in the form.** The
  answer is read once and closed, and a line inside the body moved all the
  fields below it on every check. The panel pops up above Test Connection and
  carries "Succeeded"/"Failed", details, "Copy" and a cross.
- **A stored secret is shown as `<hidden>`.** The placeholder "Leave
  unchanged" read as an empty field, and an empty field next to a saved
  connection says the password is lost. The placeholder gives way to an empty
  field the moment the field is entered — by a click or by Tab; an untouched
  field still sends nothing, and the server keeps its own.
- **The connection string appears at once when a saved connection is opened.**
  It was not visible: the client required a password that would never be sent
  to it. The rule "while editing, a secret is not required" is now named once
  (`draftSchema`) and applies both to showing the string and to saving.
- **Defaults.** Host is `localhost` (on the server side, in the options schema),
  the name of a new connection is the type's title.
- **For the file source the field is called Path**, not Folder.
- **The "copy" and "paste" buttons are raised to the field's row.** Quasar
  reserves a line under the control for an error message, so bottom alignment
  lowered them by its height.
- **The window host became shared and got resize.** All the already existing
  action forms and questions, except the **New connection** catalog, open in it.
  On first showing the frame measures its content and chooses a height within
  the viewport; after a manual resize the automatic sizing no longer interferes.
  Identical short questions and deletions get their geometry and icon from
  `shared/windows/presets.ts` rather than assembling the window anew in every
  feature.
