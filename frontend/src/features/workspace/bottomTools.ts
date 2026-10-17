import type { Component } from "vue"

import LogsTool from "@/features/logs/LogsTool.vue"
import QueriesTool from "@/features/queries/QueriesTool.vue"
import SearchIndexTool from "@/features/searchIndex/SearchIndexTool.vue"
import ManagedServices from "@/features/services/ManagedServices.vue"
import TerminalsHead from "@/features/terminals/TerminalsHead.vue"
import TerminalsTool from "@/features/terminals/TerminalsTool.vue"
import { t } from "@/shared/i18n"

export interface BottomTool {
  id: string
  /** What the head of the panel calls it. */
  title: string
  component: Component
  /** What the tool puts in the head of the panel, after its title. */
  head?: Component
}

/**
 * Everything the panel at the foot of the workspace can show (D143), one at a
 * time. A new tool is an entry here and a button that switches it through
 * `useBottomPanel` with its id. Titles are getters, read in the language
 * current when they are shown.
 */
export const BOTTOM_TOOLS: readonly BottomTool[] = [
  { id: "services", get title() { return t("workspace.bottom.services") }, component: ManagedServices },
  { id: "terminals", get title() { return t("workspace.bottom.terminals") }, component: TerminalsTool, head: TerminalsHead },
  { id: "queries", get title() { return t("workspace.bottom.queries") }, component: QueriesTool },
  { id: "logs", get title() { return t("workspace.bottom.logs") }, component: LogsTool },
  { id: "search-index", get title() { return t("workspace.bottom.search_index") }, component: SearchIndexTool },
]
