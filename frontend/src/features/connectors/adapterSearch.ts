import type { AdapterTypeInfo } from "@/client"
import { t } from "@/shared/i18n"

/**
 * Finding a source type in the catalog. Plain functions, tested without
 * mounting anything.
 *
 * What is matched, and how, is the search's (D202).
 */

/** The sidebar row that filters nothing. Not a category, so not a Category. */
export const ALL_CATEGORIES = "all"

export interface CategoryCount {
  id: string
  title: string
  count: number
}

/**
 * The types the search found, in the order it found them (D202).
 *
 * The search's source-type provider is the one place a type is matched — by
 * its name, its category, its description, the guide's short lists and the
 * services that start it — so this window keeps no rule of its own.
 */
export function inFoundOrder(types: AdapterTypeInfo[], names: string[]): AdapterTypeInfo[] {
  const byName = new Map(types.map((type) => [type.name, type]))
  return names.flatMap((name) => {
    const type = byName.get(name)
    return type === undefined ? [] : [type]
  })
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
    { id: ALL_CATEGORIES, title: t("connectors.catalog_dialog.all"), count: types.length },
    ...[...found.values()].sort((a, b) => a.title.localeCompare(b.title)),
  ]
}
