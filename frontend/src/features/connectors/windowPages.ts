import { DEFAULT_GROUP } from "@/shared/SchemaForm/jsonSchema"

/**
 * The pages of the window that edits a connection: the groups of fields the
 * source declares, then this application's own questions, in one strip rather
 * than a strip inside a strip.
 *
 * The source's pages come first, because a connection that does not connect
 * has nothing to permit. The two this application owns are there during
 * creation too — whoever registers a source is the person who knows whether
 * anybody should write through it, and asking afterwards left it open (D66).
 */
export type PageOwner = "source" | "options" | "permissions"

export interface WindowPage {
  id: string
  label: string
  /** Whose page it is: the source's own fields, or one this application owns. */
  owner: PageOwner
}

export const OPTIONS_PAGE = "options"
export const PERMISSIONS_PAGE = "permissions"

export function windowPages(groups: readonly { id: string }[]): WindowPage[] {
  const pages: WindowPage[] = groups.map((group) => ({
    id: group.id,
    // A source names its own groups and this only shows the name, capitalised
    // as a tab's first word. The one exception is the group a field falls into
    // when its model says nothing: that word is this application's, and
    // "general" says nothing about what the page holds.
    label: group.id === DEFAULT_GROUP ? "Connection" : group.id.charAt(0).toUpperCase() + group.id.slice(1),
    owner: "source",
  }))

  // Nothing stops a source from declaring a group under either name, and two
  // pages answering to one id would be one page with two contents.
  const taken = new Set(pages.map((page) => page.id))

  function own(preferred: string, label: string, owner: PageOwner): WindowPage {
    let id = preferred
    while (taken.has(id)) id = `${id}-connection`
    taken.add(id)
    return { id, label, owner }
  }

  return [
    ...pages,
    // How this connection behaves rather than how to reach it. Its own page
    // because it is nobody's first question: a connection is made to connect,
    // and how long its answers may be kept is a second thought (D105).
    own(OPTIONS_PAGE, "Options", "options"),
    own(PERMISSIONS_PAGE, "Permissions", "permissions"),
  ]
}
