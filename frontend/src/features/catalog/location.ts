import { roleOf } from "@/features/catalog/nodes"
import type { CatalogNode } from "@/features/catalog/nodes"

/** One step of the way down from the root of a connector. */
export interface Crumb {
  id: string | null
  label: string
}

/** Where a node lives, said in the terms a catalog level is set from. */
export interface Location {
  /** The steps below the root, which the level draws as a trail. */
  crumbs: Crumb[]
  /** The groupings to tick, which is how a level shows what is not a step. */
  groups: string[]
  /** The level the node lies on: the last step, or the root. */
  parentId: string | null
}

/**
 * A path of nodes read as a place on the screen. The server answers with every
 * node from the root down, and those are not crumbs: in PostgreSQL a schema is
 * a node of the path but a grouping on the screen, while a directory is a
 * level one walks into. `roleOf` decides which.
 *
 * The root is not in the path — it is the connector, and the level puts its
 * own crumb there.
 */
export function locationOf(path: CatalogNode[]): Location {
  const ancestors = path.slice(0, -1)
  const crumbs: Crumb[] = []
  const groups: string[] = []

  for (const node of ancestors) {
    if (roleOf(node) === "group") groups.push(node.id)
    else crumbs.push({ id: node.id, label: node.name })
  }

  return { crumbs, groups, parentId: crumbs[crumbs.length - 1]?.id ?? null }
}
