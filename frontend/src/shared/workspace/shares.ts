/**
 * How much of a split each of its sections takes, once the ones with nothing
 * to show are off the screen.
 *
 * A column that is on screen keeps the width it was given: `sizes` in the tree
 * are never touched, exactly as they are not touched when a column is
 * collapsed. What changes is how the room is spent right now, so bringing the
 * panel back brings the width back. See P4.
 */
export function sharesOf(sizes: number[], hidden: boolean[]): number[] {
  const shares = sizes.map(() => 0)
  let carried = 0
  let last: number | null = null

  for (const [index, size] of sizes.entries()) {
    if (hidden[index] === true) {
      carried += size
      continue
    }
    shares[index] = size + carried
    carried = 0
    last = index
  }

  // Hidden sections at the end have no next neighbour to give their share to,
  // so it goes back down the row to the last one that is showing.
  if (carried > 0 && last !== null) shares[last] = (shares[last] ?? 0) + carried
  return shares
}
