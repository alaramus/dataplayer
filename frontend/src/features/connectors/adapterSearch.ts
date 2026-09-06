import type { AdapterTypeInfo } from "@/client"

/**
 * Finding a source type in the catalog. Plain functions, tested without
 * mounting anything.
 *
 * Lexical only, and what is matched comes from the server: a type gains
 * searchable words by gaining a capability, not by anyone remembering to write
 * one down. The old application shipped an embedding model to the browser to
 * search 84 hand-written descriptions.
 */

/** The sidebar row that filters nothing. Not a category, so not a Category. */
export const ALL_CATEGORIES = "all"

export interface CategoryCount {
  id: string
  title: string
  count: number
}

/**
 * A match in the title is worth more than one further down.
 *
 * Two ranks and not five: with a closed vocabulary this size, the only
 * confusion worth resolving is "the word is its name" against "the word is
 * something it says about itself".
 */
const RANK_NAME = 0
const RANK_BODY = 1
const NO_MATCH = 2

function rankOf(type: AdapterTypeInfo, query: string): number {
  if (type.title.toLowerCase().includes(query)) return RANK_NAME
  if (type.name.toLowerCase().includes(query)) return RANK_NAME

  const body = [
    type.category_title,
    type.description,
    ...type.capabilities.map((capability) => capability.title),
  ]
  if (body.some((text) => text.toLowerCase().includes(query))) return RANK_BODY

  return NO_MATCH
}

/**
 * The types matching a query, best first.
 *
 * An empty query is not a search: the caller shows everything, or whatever
 * category is selected, rather than a list ordered by nothing.
 */
export function searchAdapters(types: AdapterTypeInfo[], query: string): AdapterTypeInfo[] {
  const needle = query.trim().toLowerCase()
  if (needle === "") return [...types]

  return types
    .map((type, index) => ({ type, index, rank: rankOf(type, needle) }))
    .filter((row) => row.rank !== NO_MATCH)
    // The index keeps the server's order — by title — among equal ranks, so
    // the list does not reshuffle for reasons a reader cannot see.
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((row) => row.type)
}

/**
 * The categories present, with how many types each holds.
 *
 * Only categories something belongs to: an empty row would invite a click
 * that empties the grid. The wording is the server's — `category_title` — so
 * the client never becomes a second place a category is named.
 */
export function categoryCounts(types: AdapterTypeInfo[]): CategoryCount[] {
  const found = new Map<string, CategoryCount>()

  for (const type of types) {
    const seen = found.get(type.category)
    if (seen) {
      seen.count += 1
    } else {
      found.set(type.category, { id: type.category, title: type.category_title, count: 1 })
    }
  }

  return [
    { id: ALL_CATEGORIES, title: "All", count: types.length },
    ...[...found.values()].sort((a, b) => a.title.localeCompare(b.title)),
  ]
}
