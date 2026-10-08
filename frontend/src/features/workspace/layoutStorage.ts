import { serverStorageKey } from "@/shared/servers/context"

/**
 * Where the workspace layout of one person is kept (D99): per person as well
 * as per server, like the tab groups and what the search opened. Local
 * storage outlives a sign-in, and the tabs one person left open must not meet
 * the next one.
 */
export const workspaceLayoutKey = (userId: string) =>
  serverStorageKey(`dataplayer-workspace:${userId}`)

/**
 * The key layouts were kept under before they were separated per person.
 * Never read any more: it may hold whoever was here before, so handing it to
 * the person here now would be the leak again. Left alone rather than moved,
 * for the same reason.
 */
export const PENDING_WORKSPACE_KEY = "dataplayer-workspace:pending"
