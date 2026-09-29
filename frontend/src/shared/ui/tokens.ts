/**
 * What the look of a control is decided by.
 *
 * The kit exposes meaning — a variant, a tone, a size — and this module is the
 * one place that turns meaning into Quasar props. It is plain functions rather
 * than component internals so the mapping can be tested without mounting
 * anything, the way `treeNodes.ts` and `rows.ts` are.
 */

/**
 * Named widths, so no screen carries an inline pixel value.
 *
 * A dialog and a standalone card are the same problem — a panel of a chosen
 * width — so they share one scale rather than each inventing its own.
 */
const PANEL_WIDTH = {
  xs: "360px",
  sm: "460px",
  md: "520px",
  lg: "900px",
} as const

export type PanelSize = keyof typeof PANEL_WIDTH

/** A wide panel needs more of a small viewport than a narrow one. */
const PANEL_MAX_WIDTH: Record<PanelSize, string> = {
  xs: "90vw",
  sm: "90vw",
  md: "90vw",
  lg: "95vw",
}

export interface PanelStyle {
  width: string
  maxWidth: string
}

export function panelStyle(size: PanelSize): PanelStyle {
  return { width: PANEL_WIDTH[size], maxWidth: PANEL_MAX_WIDTH[size] }
}

/** One height for every scrolling region, so panels do not each pick a number. */
export const SCROLL_MAX_HEIGHT = "60vh"

/**
 * What a button means, not how it looks.
 *
 * An action bar lists destructive actions beside ordinary ones, and turning
 * those into solid red buttons would shout, so a destructive action has both
 * a prominent form and a restrained one.
 *
 * `chosen` is the space you are in, on a rail of the chrome: a mark that has
 * to be found at a glance among icons on the chrome's own grey. It used to be
 * written as secondary, which in the dark theme is a grey dimmer than the
 * quiet buttons beside it, so the one you were in was the one that stood out
 * least.
 *
 * `current` is the view a panel or a window shows among its neighbours — a
 * dialect, a plan's view, 2D or 3D — or a toggle that is on. It is drawn the
 * way a current tab is (D186): filled like the main action, it was read as the
 * thing to press rather than the thing being shown.
 */
export type ButtonVariant = "primary" | "secondary" | "chosen" | "current" | "danger" | "danger-quiet" | "quiet"

/**
 * `inline` is a value in a table that opens its own editor: it reads as the
 * value, at the weight of the cells beside it, and the pointer finds the
 * button under it.
 */
export type ButtonLayout = "default" | "toolbar" | "navigation" | "inline"

/** A toolbar command and an entry of a list both keep to one line. */
export function buttonLayout(layout: ButtonLayout): { align: "left" | "center"; noWrap: boolean } {
  return { align: layout === "navigation" || layout === "inline" ? "left" : "center", noWrap: layout !== "default" }
}

export interface ButtonLook {
  color?: string
  textColor?: string
  unelevated?: boolean
  flat: boolean
}

const BUTTON_LOOKS: Record<ButtonVariant, ButtonLook> = {
  primary: { color: "dp-action-primary", textColor: "dp-on-action-primary", unelevated: true, flat: false },
  secondary: { color: "dp-action-secondary", flat: true },
  chosen: { color: "dp-action-primary", textColor: "dp-on-action-primary", unelevated: true, flat: false },
  current: { color: "dp-tab-current", textColor: "dp-action-secondary", unelevated: true, flat: false },
  danger: { color: "negative", unelevated: true, flat: false },
  "danger-quiet": { color: "dp-action-danger", flat: true },
  // Cancel and Close sit next to the action they cancel; a colour here would
  // compete with it.
  quiet: { flat: true },
}

export function buttonLook(variant: ButtonVariant): ButtonLook {
  return BUTTON_LOOKS[variant]
}

/** What a message is, not what colour it is. */
export type Tone = "error" | "success" | "warning" | "info"

export interface BannerLook {
  /** The ground and the text. */
  classes: string
  icon: string
  /** The icon says the tone even where the text does not. */
  iconClasses: string
}

// The classes are theme.css's, and turn over with the theme; Quasar's own
// colour classes are one colour for both. Every tone is a wash under the
// body's text (D187): a filled red ground left no colour for anything placed
// on it, and a transaction's countdown and its Roll back stood on it at 1.6:1.
const BANNER_ICONS: Record<Tone, string> = {
  error: "error",
  success: "check_circle",
  warning: "warning",
  info: "info",
}

/**
 * In a form the banner has no ground: the form is its ground, and its icon
 * carries the tone. An error keeps its words red, as a field's error does.
 */
export function bannerLook(tone: Tone, form = false): BannerLook {
  const icon = BANNER_ICONS[tone]
  if (!form) return { classes: toneWash(tone), icon, iconClasses: toneText(tone) }
  return { classes: tone === "error" ? toneText(tone) : "", icon, iconClasses: toneText(tone) }
}

/** A tone as a filled ground: a badge, a status dot. */
export function toneFill(tone: Tone): string {
  return `dp-tone-fill-${tone}`
}

/** A tone as a light ground under the body's text: a banner, a badge in a row. */
export function toneWash(tone: Tone): string {
  return `dp-tone-wash-${tone}`
}

/** A tone as the colour of a mark on the page: an icon, a word. */
export function toneText(tone: Tone): string {
  return `dp-tone-text-${tone}`
}

/**
 * Form fields have a permanent external label; toolbar fields stay borderless.
 * Both are marked by the one focus colour: left to Quasar, a field outside a
 * form was underlined in its brand blue.
 */
export function fieldLook(form: boolean, compact = false, error = false) {
  return {
    color: "dp-field-focus",
    dense: form || compact,
    outlined: form,
    borderless: !form && compact,
    hideBottomSpace: form || (compact && !error),
  }
}

/**
 * A tick box is marked one way everywhere (D186): the theme-aware neutral,
 * in or out of a form. Left to Quasar, a box outside a form came out in its
 * brand blue next to a form's neutral one.
 */
export function checkboxLook(form: boolean, dense: boolean) {
  return { dense: form || dense, color: "dp-control-selected" }
}

/** Switches keep the same neutral selected colour in forms and panels. */
export function toggleLook() {
  return { color: "dp-control-selected" }
}

/** A radio is marked the way a form's checkbox is: dense, and neutral when chosen. */
export function radioLook(form: boolean) {
  return checkboxLook(form, false)
}
