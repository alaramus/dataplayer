/**
 * Where the blocks of the side tool rails stand (workspace.md, Tool rails).
 *
 * Four rails, a top and a bottom half of each side; every block stands on
 * exactly one of them, in the order somebody dragged it into. Plain functions,
 * so what a stored arrangement comes to is tested without a browser; the
 * blocks themselves are in `toolBlocks`, the state and its storage in
 * `useToolRails`.
 */
export type ToolRailZone = "left-top" | "left-bottom" | "right-top" | "right-bottom"

export const ZONES: readonly ToolRailZone[] = ["left-top", "left-bottom", "right-top", "right-bottom"]

/** What the arrangement needs to know about a block. */
export interface BlockSeat {
  id: string
  /** Where it stands until somebody moves it. */
  home: ToolRailZone
  /**
   * The block it belongs next to. When a stored arrangement lacks this one —
   * it is newer than the arrangement — it joins that block wherever it was
   * put, rather than its home across the screen from it.
   */
  beside?: string
}

export type Arrangement = Record<ToolRailZone, string[]>

function empty(): Arrangement {
  return { "left-top": [], "left-bottom": [], "right-top": [], "right-bottom": [] }
}

function zoneOf(arrangement: Arrangement, id: string): ToolRailZone | undefined {
  return ZONES.find((zone) => arrangement[zone].includes(id))
}

export function defaultArrangement(blocks: readonly BlockSeat[]): Arrangement {
  const arrangement = empty()
  for (const block of blocks) arrangement[block.home].push(block.id)
  return arrangement
}

/**
 * A stored arrangement, made whole: what is not a block any more is dropped,
 * a block named twice keeps its first place, and a block it does not name
 * takes the seat it would have had. Anything unreadable is the default.
 */
export function readArrangement(raw: string | null, blocks: readonly BlockSeat[]): Arrangement {
  let parsed: unknown = null
  try {
    parsed = raw === null ? null : JSON.parse(raw)
  } catch {
    parsed = null
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return defaultArrangement(blocks)
  }
  const stored = parsed as Record<string, unknown>
  const known = new Set(blocks.map((block) => block.id))
  const placed = new Set<string>()
  const arrangement = empty()
  for (const zone of ZONES) {
    const list = stored[zone]
    if (!Array.isArray(list)) continue
    for (const entry of list) {
      const id = String(entry)
      if (!known.has(id) || placed.has(id)) continue
      placed.add(id)
      arrangement[zone].push(id)
    }
  }
  for (const block of blocks) {
    if (placed.has(block.id)) continue
    const neighbour = block.beside === undefined ? undefined : zoneOf(arrangement, block.beside)
    if (neighbour === undefined || block.beside === undefined) {
      arrangement[block.home].push(block.id)
    } else {
      const list = arrangement[neighbour]
      list.splice(list.indexOf(block.beside) + 1, 0, block.id)
    }
    placed.add(block.id)
  }
  return arrangement
}

/**
 * The arrangement with one block moved: before `before` in `zone`, or at the
 * end of it when `before` is null.
 *
 * Named by the block it lands before rather than by an index. An index into
 * the list the block is still standing in pointed one place too far whenever
 * a block was dragged down its own rail.
 */
export function moveBlock(
  arrangement: Arrangement,
  id: string,
  zone: ToolRailZone,
  before: string | null
): Arrangement {
  if (before === id) return arrangement
  const next = empty()
  for (const other of ZONES) next[other] = arrangement[other].filter((block) => block !== id)
  const target = next[zone]
  const at = before === null ? -1 : target.indexOf(before)
  if (at < 0) target.push(id)
  else target.splice(at, 0, id)
  return next
}
