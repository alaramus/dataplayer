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
 * Five rather than four: an action bar lists destructive actions beside
 * ordinary ones, and turning those into solid red buttons would shout. So a
 * destructive action has both a prominent form and a restrained one.
 */
export type ButtonVariant = "primary" | "secondary" | "danger" | "danger-quiet" | "quiet"

export type ButtonLayout = "default" | "toolbar" | "navigation"

export function buttonLayout(layout: ButtonLayout): { align: "left" | "center"; noWrap: boolean } {
  return { align: layout === "navigation" ? "left" : "center", noWrap: layout === "toolbar" }
}

export interface ButtonLook {
  color?: string
  flat: boolean
}

const BUTTON_LOOKS: Record<ButtonVariant, ButtonLook> = {
  primary: { color: "primary", flat: false },
  secondary: { color: "dp-action-secondary", flat: true },
  danger: { color: "negative", flat: false },
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
  classes: string
  icon: string
}

// The classes are theme.css's, and turn over with the theme; Quasar's own
// colour classes are one colour for both.
const BANNER_LOOKS: Record<Tone, BannerLook> = {
  error: { classes: "dp-tone-fill-error", icon: "error" },
  success: { classes: "dp-tone-fill-success", icon: "check_circle" },
  // A warning is read, not obeyed, so it stays light rather than filled.
  warning: { classes: "dp-tone-wash-warning", icon: "warning" },
  info: { classes: "dp-tone-wash-info", icon: "info" },
}

export function bannerLook(tone: Tone): BannerLook {
  return BANNER_LOOKS[tone]
}

/** A tone as a filled ground: a badge, a status dot. */
export function toneFill(tone: Tone): string {
  return `dp-tone-fill-${tone}`
}

/** A tone as the colour of a mark on the page: an icon, a word. */
export function toneText(tone: Tone): string {
  return `dp-tone-text-${tone}`
}

/** Form fields have a permanent external label; toolbar fields stay borderless. */
export function fieldLook(form: boolean, compact = false, error = false) {
  return {
    dense: form || compact,
    outlined: form,
    borderless: !form && compact,
    hideBottomSpace: form || (compact && !error),
  }
}
