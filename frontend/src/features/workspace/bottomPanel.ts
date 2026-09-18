/**
 * The panel along the foot of the workspace (D143): which tool it shows and
 * how tall it is. Plain functions, so what a stored state comes to is tested
 * without a browser; the tools are in `bottomTools`, the state and its
 * storage in `useBottomPanel`.
 */
export interface BottomPanelState {
  /** The tool shown, or null while the panel is hidden. */
  open: string | null
  height: number
}

export const BOTTOM_PANEL_DEFAULT_HEIGHT = 260
export const BOTTOM_PANEL_MIN_HEIGHT = 120

export function defaultBottomPanel(): BottomPanelState {
  return { open: null, height: BOTTOM_PANEL_DEFAULT_HEIGHT }
}

/**
 * A stored state, made whole: a tool that is not one any more is no tool, and
 * a height that is not a number is the default. Anything unreadable is the
 * default.
 */
export function readBottomPanel(raw: string | null, tools: readonly string[]): BottomPanelState {
  let parsed: unknown = null
  try {
    parsed = raw === null ? null : JSON.parse(raw)
  } catch {
    parsed = null
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return defaultBottomPanel()
  }
  const stored = parsed as Record<string, unknown>
  const open = typeof stored.open === "string" && tools.includes(stored.open) ? stored.open : null
  const height =
    typeof stored.height === "number" && Number.isFinite(stored.height)
      ? clampBottomPanelHeight(stored.height)
      : BOTTOM_PANEL_DEFAULT_HEIGHT
  return { open, height }
}

/**
 * Pressing a tool's button shows it, or hides the panel when it is the one
 * already shown — the rail button is the tool's own switch, as in an IDE.
 */
export function toggleTool(state: BottomPanelState, tool: string): BottomPanelState {
  return { ...state, open: state.open === tool ? null : tool }
}

/**
 * Only a floor: the ceiling is the room above, which only the layout knows,
 * so the card holds it with a `max-height` and a drag starts from the height
 * the card is actually drawn at.
 */
export function clampBottomPanelHeight(height: number): number {
  return Math.max(BOTTOM_PANEL_MIN_HEIGHT, Math.round(height))
}
