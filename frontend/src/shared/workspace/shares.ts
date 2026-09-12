/**
 * How much of a split each of its sections takes, once the ones with nothing
 * to show are off the screen.
 *
 * A share is a flex grow factor, which is a ratio: leaving the sections that
 * stay with the sizes they were given already spreads the room of the ones
 * that went over them, in proportion to what each already has. They are
 * scaled back to a hundred so that a share still reads as a percentage of the
 * split, and so that factors adding up to less than one cannot leave part of
 * the row empty.
 *
 * `sizes` in the tree are never touched, exactly as they are not touched when
 * a column is collapsed, so bringing the panel back brings the width back.
 *
 * The room used to go whole to the next section along, which is what a row of
 * three columns wants: the narrow list of connections did not widen because
 * the catalog went. But a split running the same way as its parent is
 * flattened into it (tree.ts), so "the next one along" is one work card out of
 * several — and a card carrying room freed by somebody else cannot be dragged
 * narrower than that room, which is the border moving while the card does not.
 * See P4.
 */
export function sharesOf(sizes: number[], hidden: boolean[]): number[] {
  const showing = sizes.reduce(
    (sum, size, index) => (hidden[index] === true ? sum : sum + size),
    0
  )
  if (showing <= 0) return sizes.map(() => 0)
  return sizes.map((size, index) => (hidden[index] === true ? 0 : (size * 100) / showing))
}
