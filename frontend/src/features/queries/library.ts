import { ref } from "vue"

/**
 * What the query library is showing, kept while the panel at the foot of the
 * screen is hidden (D143): its body is unmounted then, and coming back to a
 * different place and connection than it was left on read as losing work.
 *
 * Module state, as the bottom panel's own is: the button on the rail aims the
 * library at the open connection, and the body lists what it is aimed at.
 */
export type LibraryPlace = "favorites" | "history"

const place = ref<LibraryPlace>("favorites")
const connectorId = ref<string | null>(null)

export function useQueriesLibrary() {
  return {
    place,
    connectorId,
    /**
     * Filter to the connection the library was opened from. Nothing open
     * leaves the filter as it was rather than widening it to everything.
     */
    aim: (connector: string | null) => {
      if (connector !== null) connectorId.value = connector
    },
  }
}
