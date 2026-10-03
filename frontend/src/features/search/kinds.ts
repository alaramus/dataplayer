import type { ObjectTarget } from "@/client"
import { appIcons } from "@/shared/ui/icons"

/**
 * The kinds of thing the application keeps, as a screen draws and names them.
 *
 * Records over the generated union: a kind the server adds fails to compile
 * here until it has an icon and a word.
 */
export type ObjectType = ObjectTarget["object_type"]

export const OBJECT_ICONS: Record<ObjectType, string> = {
  saved_query: appIcons.star,
  pipeline: appIcons.accountTree,
  dashboard: appIcons.dashboard,
  conversation: appIcons.robot2,
  quick_chat: appIcons.quickChat,
  project: appIcons.folder,
  service: appIcons.dns,
  ssh_key: appIcons.sshKey,
  guide_page: appIcons.menuBook,
  source_type: appIcons.storage,
  tab: appIcons.tab,
  tab_group: appIcons.bookmarks,
}

export const OBJECT_LABELS: Record<ObjectType, string> = {
  saved_query: "Saved query",
  pipeline: "Pipeline",
  dashboard: "Dashboard",
  conversation: "Conversation",
  quick_chat: "Quick chat",
  project: "Project",
  service: "Service",
  ssh_key: "SSH key",
  guide_page: "Guide page",
  source_type: "Source type",
  tab: "Tab",
  tab_group: "Tab group",
}

/** Whether a fact's kind is one of the application's own. */
export function isObjectType(kind: string): kind is ObjectType {
  return Object.hasOwn(OBJECT_LABELS, kind)
}
