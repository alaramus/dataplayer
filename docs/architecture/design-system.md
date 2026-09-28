# Design system

What a size of text, a height, an icon and a colour of text are worth, and
which one a role spends. Read this before giving anything on screen a size, a
weight, an icon size or a text colour of its own. How screens are built and
what the kit is, is in [frontend.md](frontend.md); the neutral window forms
are D131 there.

Decisions here: D185.

```
frontend/src/
├── quasar-variables.sass     the scale said again for Quasar's own components
├── main.ts                   ships Inter with the bundle
└── shared/ui/
    ├── metrics.css           sizes: type, lines, icons, controls, rows, spacing, corners
    ├── typography.css        roles: overline, helper, meta, section and page titles; tag resets
    ├── theme.css             colours, the text colours and the focus ring among them
    └── typography.spec.ts    fails on a size or a weight spent past the scale
```

## D185. Type, geometry and icons are one scale, and Quasar is told it

The kit owns the look of text and controls; Quasar's own components are
configured from the same numbers rather than left at their defaults. The
audit of 2026-09-28 found the chrome at 13px and every button and field at
Quasar's 14px, a button 36px beside a 32px field, a button's corner 3px beside
a field's 4px, and Quasar's document heading styles leaking a 50px line into
every `<h3>` of the chrome.

- **One face, shipped.** Inter comes with the bundle (`@fontsource-variable/inter`,
  weight axis, normal and italic). Declared and not shipped, it had fallen
  through to Segoe UI on Windows and to whatever else elsewhere.
- **Seven sizes, each a role**: `xs` 11px for a count, a caption, an overline
  and a badge; `sm` 12px for help under a control, an error, a tooltip and a
  toast; 13px for the chrome, controls included; `lg` 15px for the title of a
  panel about one thing; `page` 20px; `display` 24px for a number that is a
  whole widget; `mono` 12px for the editor, a log and a value read character
  by character. Prose keeps its own 15/14px and heading sizes. Lines are
  pixels — 20px for the body, 16px for the small sizes when they wrap, 28px
  for a page title, 18px for mono — so a row lands on whole pixels.
- **Three weights**: 400 text, 500 a title of a card or window, the current
  tab and a button, 600 a section, an overline and a table heading. A
  browser's bold is 700 and is reset to 600 for `b`, `strong` and `th`.
- **Roles are classes** in `typography.css`: `dp-overline`, `dp-helper`,
  `dp-meta`, `dp-section-title`, `dp-page-title`. A screen carries the role
  rather than restating its size, weight and spacing. `h1`–`h6` are reset to
  inherit everything; their look is the class they carry.
- **One control height, 32px**, for a field, a button, an icon button and a
  toolbar field alike; 20px for a control inside a dense row. A toolbar field
  names itself beside it or by its placeholder, never by a label floated over
  its value. Rows are 24px dense or 32px ordinary; both kinds of tab are 26px.
- **Three icon sizes**: 16px inside a line of text, 20px for a control of its
  own, 24px for a source's logo and an empty panel; 32px only for the logo
  heading a panel about one source and an empty conversation. Quasar's button
  icon follows the button's line (1.5385em), so a compact button shrinks its
  icon with it.
- **Three text colours**: `--dp-text` (.87) for everything read, `--dp-text-muted`
  (.6) for secondary text and as the floor for anything a person must read,
  `--dp-text-faint` for marks that are not text. The token that had been
  called strong was the weakest of the three and is gone.
- **One focus ring**: 2px of `--dp-focus-border` just outside the control.

Enforced by `typography.spec.ts`, which fails on a `font-size` in a component
that is not a type or icon token, on a weight other than 400/500/600, and on a
pixel size handed to an element from a script. Verified by breaking each.

Known deviations:

- **The terminal is 13px.** xterm takes a number, and a terminal is read as a
  screen of cells rather than as code in the chrome.

Spec: [The UI audit and its corrections](../decisions/2026-09-28-ui-audit-design.md)
