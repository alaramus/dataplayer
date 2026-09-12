/**
 * How much of a split each of its sections takes, once the ones with nothing
 * to show are off the screen.
 *
 * The room of a section that is off the screen goes to the sections after it,
 * shared out in proportion to what each already has. Forward, so that a narrow
 * column keeps its width when the wide one beside it goes: the list of
 * connections is a fifth of the screen because the user made it one, and the
 * catalog leaving is no reason for it to swell. In proportion rather than
 * whole to the first of them, because a split running the same way as its
 * parent is flattened into it (tree.ts), so "the next one along" is one work
 * card out of several - and a card given room freed by somebody else can never
 * be dragged narrower than that room: the border stops and the card stays as
 * wide as the column that went.
 *
 * Nothing after it leaves the section before it to take the room whole. It is
 * the one case where the floor above remains, and it is the harmless one: the
 * only border left is the one that would have to be dragged nearly across the
 * screen to reach it.
 *
 * `sizes` in the tree are never touched, exactly as they are not touched when
 * a column is collapsed, so bringing the panel back brings the width back.
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
  const showing = sizes.flatMap((_, index) => (hidden[index] === true ? [] : [index]))
  const shares = sizes.map((size, index) => (hidden[index] === true ? 0 : size))
  const gaps = sizes.map(() => 0)
  // Every index here comes from `sizes` itself, so nothing is out of bounds -
  // which the compiler cannot see through an index, hence the one place the
  // fallback is written.
  const add = (into: number[], index: number, amount: number) => {
    into[index] = (into[index] ?? 0) + amount
  }

  for (const [index, size] of sizes.entries()) {
    if (hidden[index] !== true) continue
    const after = showing.filter((other) => other > index)
    const room = after.reduce((sum, other) => sum + (sizes[other] ?? 0), 0)
    if (room > 0) {
      for (const other of after) add(shares, other, (size * (sizes[other] ?? 0)) / room)
      const first = after[0]
      if (first !== undefined) add(gaps, first, 1)
      continue
    }
    const previous = showing.filter((other) => other < index).at(-1)
    if (previous !== undefined) {
      add(shares, previous, size)
      add(gaps, previous, 1)
    }
  }

  return sizes.map((_, index) => ({ share: shares[index] ?? 0, gaps: gaps[index] ?? 0 }))
}
