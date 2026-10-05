/**
 * Whether the layout gained a panel between two readings of its ids.
 *
 * Bringing Data forward is for what arrives by another way — a restored tab
 * group, a panel opened from the search or the agent — and not for what only
 * leaves: closing a window over another space removes its panel, and calling
 * Data forward for that takes the person away from where they were, with
 * nothing new to look at.
 */
export function gainedPanels(before: readonly string[], after: readonly string[]): boolean {
  const known = new Set(before)
  return after.some((id) => !known.has(id))
}
