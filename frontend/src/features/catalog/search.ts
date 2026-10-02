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
    const match = matches[index]
    const location = match?.location ?? ""
    // The line the words were found on replaces what the row would otherwise
    // say about itself: the size of a file matters less than the hit in it,
    // and a search inside files that showed neither would be a list of names.
    const excerpt = match?.excerpt ?? null
    const found = excerpt === null ? row : { ...row, caption: excerpt }
    return location === "" ? found : { ...found, location }
  })
  return {
    query,
    rows,
    complete: result.complete !== false,
    // A failure's sentence is the error banner's to say, once.
    notice: result.error_kind == null ? result.notice ?? null : null,
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
