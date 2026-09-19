import type { Component } from "vue"

import ManagedServices from "@/features/services/ManagedServices.vue"
import TerminalsTool from "@/features/terminals/TerminalsTool.vue"

export interface BottomTool {
  id: string
  /** What the head of the panel calls it. */
  title: string
  component: Component
}

/**
 * Everything the panel at the foot of the workspace can show (D143), one at a
 * time. A new tool is an entry here and a button that switches it through
 * `useBottomPanel` with its id.
 */
export const BOTTOM_TOOLS: readonly BottomTool[] = [
  { id: "services", title: "Services", component: ManagedServices },
  { id: "terminals", title: "Terminals", component: TerminalsTool },
]
