import { readonly, ref } from "vue"

import { TOOL_BLOCKS } from "./toolBlocks"
import { moveBlock, readArrangement } from "./toolRails"
import type { Arrangement, ToolRailZone } from "./toolRails"

const STORAGE_KEY = "dataplayer-tool-rails"

function stored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

// One arrangement for the four rails: a block dragged from one to another
// leaves one and joins the other in a single write.
const arrangement = ref<Arrangement>(readArrangement(stored(), TOOL_BLOCKS))

/** The blocks of the side tool rails and where each stands, kept per browser. */
export function useToolRails() {
  function place(id: string, zone: ToolRailZone, before: string | null) {
    arrangement.value = moveBlock(arrangement.value, id, zone, before)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(arrangement.value))
    } catch {
      // Losing the arrangement to a full or blocked storage loses nothing else.
    }
  }

  return { arrangement: readonly(arrangement), place }
}
