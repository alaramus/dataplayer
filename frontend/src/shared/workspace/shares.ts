/**
 * How much of a split each of its sections takes, once the ones with nothing
 * to show are off the screen.
 *
 * The room of a section that is off the screen goes to the sections after it,
 * shared out in proportion to what each already has. Forward, so that a narrow
 * column keeps its width when the wide one beside it goes: the list of
 * connections is a fifth of the screen because the user made it one, and the
 * catalog leaving is no reason for it to swell. In proportion, so that every
 * section is drawn a fixed multiple of its size: a border is then dragged in
 * what the screen shows rather than in sizes (`tradeShares`), and no card
 * holding room freed by somebody else is stuck at least that wide.
 *
 * Nothing after it leaves the section before it to take the room whole.
 *
 * `sizes` in the tree are not touched here, exactly as they are not touched
 * when a column is collapsed, so bringing the panel back brings the width
 * back - or, after a border was dragged meanwhile, the same part of the room.
 * See P4.
 */

export interface Share {
  /** Its part of the room the sections that are showing divide between them. */
  share: number
  /**
   * How many sections that are not drawn it stands in for.
   *
   * One of them takes a border and its own two edges off the row, so the row
   * spends that many pixels less. They are given back as a fixed part of a
   * section's width rather than as a share of the row, which is what keeps the
   * columns in front of it exactly as wide as they were rather than a pixel or
   * two wider until it comes back.
   *
   * Whole to the first section that takes its room, and not shared out as the
   * room itself is: a basis that moved with the sizes would move while a
   * border is dragged, and the border would run ahead of the pointer.
   */
  gaps: number
}

export function sharesOf(sizes: number[], hidden: boolean[]): Share[] {
  const shares = sizes.map((size, index) => (hidden[index] === true ? 0 : size))
  const gaps = sizes.map(() => 0)
  // Every index here comes from `sizes` itself, so nothing is out of bounds -
  // which the compiler cannot see through an index, hence the one place the
  // fallback is written.
  const add = (into: number[], index: number, amount: number) => {
    into[index] = (into[index] ?? 0) + amount
  }

  for (const lender of lendersOf(sizes, hidden)) {
    for (const index of lender.to) add(shares, index, lentTo(lender, sizes[index] ?? 0))
    const first = lender.to[0]
    if (first !== undefined) add(gaps, first, 1)
  }

  return sizes.map((_, index) => ({ share: shares[index] ?? 0, gaps: gaps[index] ?? 0 }))
}

/**
 * Move the border between two sections on the screen by `delta` of the room
 * they divide, and answer with the sizes that draw it; null when it cannot
 * move.
 *
 * The delta and both minimums are shares as `sharesOf` gives them - what the
 * screen shows, which is what a pixel converts to. Sizes are what the tree
 * keeps, and with a section off the screen the two differ: a section that took
 * its room is that room wider than its size. Traded in sizes, a card holding
 * the whole room of a column on the bar could never be dragged narrower than
 * that room, because its own size ran out first.
 *
 * So a section off the screen keeps the part of the room it lent rather than
 * its size: as the sections it lent to grow or shrink, it does with them. That
 * keeps every other section on the screen where it was, and brings the one on
 * the bar back as the same part of that room it left.
 */
export function tradeShares(
  sizes: number[],
  hidden: boolean[],
  beforeIndex: number,
  afterIndex: number,
  delta: number,
  minBefore: number,
  minAfter: number
): number[] | null {
  const shares = sharesOf(sizes, hidden)
  const before = shares[beforeIndex]?.share
  const after = shares[afterIndex]?.share
  if (before === undefined || after === undefined) return null

  const room = before + after
  const clamped = Math.min(Math.max(before + delta, minBefore), room - minAfter)
  if (!Number.isFinite(clamped) || clamped <= 0 || room - clamped <= 0) return null

  const lenders = lendersOf(sizes, hidden)
  // A section is drawn this many times its size: once, and the part of every
  // room lent to it, which is in proportion to its size.
  const factorOf = (index: number) =>
    lenders.reduce(
      (sum, lender) => (lender.to.includes(index) ? sum + lender.size / lender.room : sum),
      1
    )

  const next = [...sizes]
  next[beforeIndex] = clamped / factorOf(beforeIndex)
  next[afterIndex] = (room - clamped) / factorOf(afterIndex)
  for (const lender of lenders) {
    const now = lender.to.reduce((sum, index) => sum + (next[index] ?? 0), 0)
    next[lender.index] = (lender.size * now) / lender.room
  }
  return next.every((size) => Number.isFinite(size)) ? next : null
}

/** A section off the screen, and the sections on it that take its room. */
interface Lender {
  index: number
  size: number
  /** Those after it, or failing them the one before; the first takes its gap. */
  to: number[]
  /** Their sizes together. */
  room: number
}

function lendersOf(sizes: number[], hidden: boolean[]): Lender[] {
  const showing = sizes.flatMap((_, index) => (hidden[index] === true ? [] : [index]))
  const sum = (indices: number[]) =>
    indices.reduce((total, index) => total + (sizes[index] ?? 0), 0)
  return sizes.flatMap((size, index) => {
    if (hidden[index] !== true) return []
    const after = showing.filter((other) => other > index)
    if (sum(after) > 0) return [{ index, size, to: after, room: sum(after) }]
    const previous = showing.filter((other) => other < index).at(-1)
    if (previous === undefined) return []
    return [{ index, size, to: [previous], room: sum([previous]) }]
  })
}

/** Whole when those it lends to have no size to share it out by. */
function lentTo(lender: Lender, size: number): number {
  return lender.room > 0 ? (lender.size * size) / lender.room : lender.size
}
