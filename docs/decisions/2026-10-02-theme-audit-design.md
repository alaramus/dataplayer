# The theme audit and its corrections

Date: 2026-10-02. Decision: D196.

## The problem

The application has seven palettes — Light, Dark, and five named themes —
and System, which picks Light or Dark. Components never write a colour of
their own (`palette.spec.ts`), so every question about colour is a question
about `theme.css`. The audit resolved each theme from that file as the browser
cascades it, laid every translucent token over the ground it sits on, and
measured the result against WCAG 2.2.

Light and Dark had been tuned by hand and mostly held. The named themes were
partial overrides of them, picked by eye, and nothing measured them:

- **Text below 4.5:1 where it is read.** The link was `rgba(25,118,210,.9)`,
  3.9:1 over white, in grid cells, Markdown and the catalog; Paper light's
  link 4.0:1; its tab captions 4.2:1 on the tab fills, because its muted text
  had been picked for the surface. Light's accent was 4.4:1 in a window.
- **A field's error at 2.9:1 in every dark theme.** Quasar writes the message,
  the outline and the icon of a field in error in its negative, `#c10015`,
  a fill colour.
- **Marks under 3:1.** Field borders were 1.46–1.94:1 in all seven themes;
  Light's faint marks 2.4:1; Paper light's drop target 2.4:1.
- **A chosen row indistinguishable from a hovered one** in Light: 1.04:1.
- **Three themes in the reverse order of grounds.** Paper, Midnight and Dark
  purple came from rich-md-viewer, where the darkest value is the document's
  canvas; here it became the frame, below the card's surface. Their card head
  was the window bar's token mixed 18% towards the text — done so that a
  window's bar would stand off its frame — which made every card's head the
  brightest thing on the screen (L* 30 against 8–11), brighter than the tabs
  on it, and put secondary text on it at 4.0–4.1:1. Dark blue had the
  opposite fault: its window bar was darker than the window.
- **Info borrowed the accent.** In Paper and Paper light a note was bronze,
  8–10° of hue from the amber warning; in Dark purple it was pink, 32° from
  the salmon error. Paper light's banners were Light's washes, drawn for
  white, at 1.03–1.08:1 on cream.
- **Two themes with one character.** Dark blue overrode ten tokens, its
  grounds only, and kept Dark's sky-blue accent; Midnight's ice blue was ΔE
  8.4 from it. Midnight was meant as the deep one and was lighter than Dark,
  with brighter text.
- **Paper was a dark theme** beside one called Paper light, and read as the
  light one.
- **The first frame was always light**: the theme is applied by the bundle.

## The decision

- **Floors, enforced.** `contrast.spec.ts` resolves every theme and holds:
  text and secondary text at 4.5:1 on every ground a card is built of; link,
  accent and note at 4.5:1 on the surface, a window and a head; every tone at
  4.5:1; the focus ring, a field's border, a faint mark and a drop target at
  3:1; a chosen row 1.1:1 from a hover; a banner 1.08:1 from the page.
- **One order of grounds.** Measured from the surface towards the middle, in
  both polarities: the frame and the head beyond the surface, the tabs beyond
  the head, the window bar beyond its window. The window bar (`--dp-chrome`)
  and the card head (`--dp-card-head`) are separate in every named theme. The
  dark ones step as Dark does, about +5, +10 and +16 L* from the surface for
  head, frame and tabs.
- **Info is its own tone**, `--dp-info`, at least 60° of hue from warning and
  error. Blue in every theme; a theme's accent stays its own.
- **A named theme declares** its grounds, accent family and note in its own
  rule. Text, borders and the other tones may come from Light or Dark.
- **A chosen row has an edge**, `--dp-selected-edge`, the accent along its
  leading side; the wash is .16 in Light.
- **Quasar follows the theme.** `--q-negative` is `--dp-danger-fill` (lighter,
  `#d32f2f`, in the dark themes), and inside a field in error it is the error
  text. `--q-dark` and `--q-dark-page` are the raised ground and the frame.
- **Dark blue and Midnight are kept and separated** rather than one removed.
  Dark blue keeps its saturated navy and takes a cyan accent family: the
  vernacular of technical tools, and no longer blue on blue. Midnight becomes
  the dimmest theme: a near-black navy ground, text at `#cdd9e8` (13.6:1),
  ice-blue accent. Removing one was the alternative; once they differ in
  brightness and accent each has a use.
- **Paper is labelled Paper dark.** Its id stays `paper`, so a stored choice
  still finds it. Preferences lists light themes, then dark, then System,
  from one `THEMES` registry in `stores/theme.ts`.
- **The theme is on the page before the first paint.** An inline script in
  `index.html` reads the same stored choice and the system's preference;
  `theme.spec.ts` holds its list of ids to the registry.
- **The toggle returns** to the last light or dark theme chosen, Light or
  Dark when none was, and its tooltip names the theme.
- **The current tab of `AppTabs`** carries the line under it that a workspace
  tab has; on a light head its ground alone was 1.1:1.

## Not done

- **A border on the front window in the dark themes.** D131 marks the front
  window by its shadow only, having tried a border of its own and found it
  read as a thicker frame. The weakness on dark grounds stays a known
  deviation of D186.
- **Deriving the ladder with `color-mix`.** Every theme would declare a ground
  and an ink and the steps would follow. The values here were computed as
  equal L* steps instead; the order is held by the test either way, and the
  derivation can replace the numbers without changing the contract.
- **Renaming the tone tokens** to one scheme (`--dp-status-*`). Four naming
  schemes for one family remain; renaming touches every screen for no
  change on it.
