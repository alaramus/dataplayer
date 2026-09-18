import { computed, ref } from "vue"

import { clampBottomPanelHeight, readBottomPanel, toggleTool } from "./bottomPanel"
import type { BottomPanelState } from "./bottomPanel"
import { BOTTOM_TOOLS } from "./bottomTools"

const STORAGE_KEY = "dataplayer-bottom-panel"

function stored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

// One state for the panel and for every button that switches it: the button
// stands on a rail and the panel under the columns, and neither owns the other.
const state = ref<BottomPanelState>(readBottomPanel(stored(), BOTTOM_TOOLS.map((tool) => tool.id)))

function write(next: BottomPanelState) {
  state.value = next
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Losing the panel to a full or blocked storage loses nothing else.
  }
}

/** The panel at the foot of the workspace (D143), kept per browser. */
export function useBottomPanel() {
  return {
    open: computed(() => state.value.open),
    height: computed(() => state.value.height),
    toggle: (tool: string) => {
      write(toggleTool(state.value, tool))
    },
    hide: () => {
      write({ ...state.value, open: null })
    },
    setHeight: (height: number) => {
      write({ ...state.value, height: clampBottomPanelHeight(height) })
    },
  }
}
