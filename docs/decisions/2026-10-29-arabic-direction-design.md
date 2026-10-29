# Arabic, the first language read right to left

Date: 2026-10-29. Decision: D281.

The interface spoke seven languages, all written left to right. Arabic is the
eighth and the first that reads the other way, so translating its words is only
half the work: every margin, border, scrollbar and row that was placed with a
physical side would stay where it was, and a left-aligned Arabic sentence with
its punctuation on the wrong end is not translated text.

## Direction belongs to the document

The direction of a page is a property of the page, not of a screen. Quasar's
own Arabic pack already says `rtl: true` and sets `<html dir>` when its
language is applied, and the browser knows the direction of the text before any
application code runs. Two owners of that attribute would disagree during the
first frame and after a language switch, so there is one: the document.

`index.html` sets `lang` and `dir` in a small script before the first paint,
from the language the browser remembers (`dataplayer-language`). The application
is mounted only after that language's chunk has loaded, so the first frame is
already in the right direction. `applyLanguage` sets the same two attributes
when the account's language is read or chosen, covering the switch without a
reload. Everything else follows from `<html dir="rtl">`: flex rows run the other
way, the scrollbar changes sides, and a logical margin lands on the other edge.

A screen does not set `dir` on its own root. The exception is a surface whose
content is not prose, and those are pinned below.

## Logical properties instead of a second stylesheet

The alternative was a direction-specific override block, or a mirrored copy of
the layout. Both drift: a new screen is written once and looks right in one
direction, and the override is discovered missing only when somebody reads the
interface in Arabic. Logical properties make the ordinary rule correct in both
directions, so a screen written later needs no direction work at all.

Spacing and alignment under `frontend/src` use `margin-inline-start` and
`-end`, `padding-inline-*`, `border-inline-*`, `inset-inline-*`, and
`text-align: start` or `end`. This touched sixty-seven files, most of them a
single declaration; the diff is mechanical and the visual result in English is
unchanged.

A physical side survives where it does not mean "the text's side". A centred
overlay keeps `left: 50%` because `translateX(-50%)` undoes it and a logical
`inset-inline-start` would move the centre. An icon that must not mirror — a
play triangle, a logo — stays as drawn. Each such place says why it is
physical.

## Code stays left to right

A path, a SQL statement and a shell's output are not Arabic prose. Mirrored,
`SELECT * FROM t;` puts its semicolon at the left and a file path reads
backwards; a terminal's cursor and column positions assume left to right as
well. The editor and a Markdown code fence therefore set `dir: "ltr"` on
CodeMirror's content attributes, and a terminal's screen carries `dir="ltr"`
beside its other host attributes (D149). The surrounding labels and prose still
follow the page.

Any later surface that shows code, a diff, a path or a terminal does the same;
the rule is that direction follows the content, and code's content is left to
right in every language.

## What else Arabic needed

- Its dictionary under `frontend/src/shared/i18n/locales/ar/`, typed against
  the English like every other language (D224), plus `problems.ts` for the
  coded refusals and a `glossary.md` agreeing one word per thing.
- Its six plural forms, `zero | one | two | few | many | other`, in
  `PLURAL_FORMS`; the browser's `Intl.PluralRules` chooses among them.
- The server's catalogs, `ar.py` in every package that keeps one, and the
  guide's Arabic pages (D227). The merged catalog rule still holds: one English
  sentence has one Arabic translation everywhere.
- ECharts' Arabic pack, registered beside its other locales.
- Dates and numbers: the day period, order and separators come from the `ar`
  locale; digits stay the Western `0`–`9` the data uses, as the glossary says.
- Tests: an Arabic browser sets `lang="ar"` and `dir="rtl"`, English leaves
  `dir="ltr"`, Arabic digits are formatted in Arabic, and every dictionary
  compiles and keeps the English key tree.

## Known limits

- A translated page that does not exist yet falls back to English (D227); the
  English paragraph inside an Arabic page is still laid out right to left, as
  the page is.
- Data shown in a grid is the source's own text and is not reordered; a cell
  holding Arabic follows the cell's direction, a cell holding a path does not
  get its own rule.
- A chart keeps the locale and direction it was drawn with until it is drawn
  again (D227).
