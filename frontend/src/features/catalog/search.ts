import type { NodeSearchResult } from "@/client"
import { toListNodes } from "@/features/catalog/nodes"
import type { ListNode } from "@/features/catalog/nodes"

/**
 * What a search left on the screen.
 *
 * The query is kept beside the rows because the list stops being a level while
 * this is here: the head has to say what is being shown and offer the way back
 * to the folder (D76).
 */
export interface FoundNodes {
  query: string
  rows: ListNode[]
  complete: boolean
  notice: string | null
}

/**
 * Matches as rows of the same list a level is drawn in.
 *
 * The node goes through `toListNodes`, so a found row has the icon, the
 * caption and the role its level would have given it — a folder is walked
 * into, a file opens what it opens. All that is added is where it was found,
 * in the source's own words.
 */
export function foundNodes(query: string, result: NodeSearchResult): FoundNodes {
  const matches = result.matches ?? []
  const rows = toListNodes(matches.map((match) => match.node)).map((row, index) => {
    const location = matches[index]?.location ?? ""
    return location === "" ? row : { ...row, location }
  })
  return {
    query,
    rows,
    complete: result.complete !== false,
    notice: result.notice ?? null,
  }
}

/**
 * What the head says while search results are shown.
 *
 * Two states rather than one number: a search that found everything and a
 * search that stopped looking are different answers, and only the second is a
 * reason to type more words.
 */
export function searchSummary(found: FoundNodes): string {
  const count = found.rows.length
  if (count === 0) return `Nothing matches “${found.query}”`
  const noun = count === 1 ? "match" : "matches"
  if (found.complete) return `${String(count)} ${noun} for “${found.query}”`
  return `First ${String(count)} ${noun} for “${found.query}”`
}
