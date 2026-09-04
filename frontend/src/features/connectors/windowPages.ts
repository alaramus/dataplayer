import { DEFAULT_GROUP } from "@/shared/SchemaForm/jsonSchema"

/**
 * The pages of the window that edits a connection.
 *
 * Two vocabularies meet in one strip. The source declares groups of its own
 * fields — an address here, a tunnel there — and this application has one
 * question that is not the driver's at all: who may reach this connection, and
 * what may be done through it. Both are pages of the same window, so they
 * share one strip rather than nesting a strip inside a strip.
 *
 * The source's pages come first, because that is what the window is for: a
 * connection that does not connect has nothing to permit. The last page is
 * always there, including while a connection is being created — whoever
 * registers a source is the person who knows whether anybody should be able
 * to write through it, and asking afterwards left it open until they went
 * back (D66).
 */
export interface WindowPage {
  id: string
  label: string
  /** Whether this is the page this application owns rather than the source. */
  permissions: boolean
}

export const PERMISSIONS_PAGE = "permissions"

export function windowPages(groups: readonly { id: string }[]): WindowPage[] {
  const pages = groups.map((group) => ({
    id: group.id,
    // A source names its own groups and this only shows the name. The one
    // exception is the group a field falls into when its model says nothing:
    // that word is this application's, and "general" says nothing about what
    // the page holds.
    label: group.id === DEFAULT_GROUP ? "Connection" : group.id,
    permissions: false,
  }))

  // Nothing stops a source from declaring a group under this name, and two
  // pages answering to one id would be one page with two contents.
  const taken = new Set(pages.map((page) => page.id))
  let id = PERMISSIONS_PAGE
  while (taken.has(id)) id = `${id}-connection`
  return [...pages, { id, label: "Permissions", permissions: true }]
}
