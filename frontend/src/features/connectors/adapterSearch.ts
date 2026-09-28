import type { AdapterTypeInfo, ServiceTemplateInfo } from "@/client"

/**
 * Finding a source type in the catalog. Plain functions, tested without
 * mounting anything.
 *
 * Lexical only, and what is matched comes from the server: the name, the
 * description, and the short lists of the type's page in the guide (D183).
 * The old application shipped an embedding model to the browser to search 84
 * hand-written descriptions.
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

function rankOf(
  type: AdapterTypeInfo,
  query: string,
  startable: ServiceTemplateInfo[]
): number {
  if (type.title.toLowerCase().includes(query)) return RANK_NAME
  if (type.name.toLowerCase().includes(query)) return RANK_NAME

  const body = [
    type.category_title,
    type.description,
    // What the panel says it can do, in the words the panel says it in: a
    // match on a capability nobody is shown would be one nobody can explain.
    ...(type.can_see ?? []),
    ...(type.can_change ?? []),
    // What this server can start of this type is something it says about
    // itself too. TimescaleDB is a PostgreSQL here (D119), so somebody who
    // looks for it by name would otherwise be told that no source type
    // matches - and the one place it can be started from is the panel of a
    // type they were given no reason to open.
    ...startable.flatMap((template) => [template.title, template.description]),
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
export function searchAdapters(
  types: AdapterTypeInfo[],
  query: string,
  startable: ServiceTemplateInfo[] = []
): AdapterTypeInfo[] {
  const needle = query.trim().toLowerCase()
  if (needle === "") return [...types]

  return types
    .map((type, index) => ({
      type,
      index,
      rank: rankOf(
        type,
        needle,
        startable.filter((template) => template.adapter_type === type.name)
      ),
    }))
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
