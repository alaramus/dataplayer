import type { Component } from "vue"

import ManagedServices from "@/features/services/ManagedServices.vue"

export interface BottomTool {
  id: string
  /** What the head of the panel calls it. */
  title: string
  component: Component
}

/**
 * Everything the panel at the foot of the workspace can show (D143), one at a
 * time. A new tool is an entry here and a button that calls
 * `useBottomPanel().toggle` with its id; terminals are the next expected.
 */
export const BOTTOM_TOOLS: readonly BottomTool[] = [
  { id: "services", title: "Services", component: ManagedServices },
]
