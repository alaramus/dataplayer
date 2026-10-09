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
 * Keys a layout was kept under for everyone using the browser: before the
 * separation per person, and briefly while the person was not known yet.
 * Never read, since they may hold whoever was here before.
 */
const SHARED_LAYOUT_KEYS = ["dataplayer-workspace", "dataplayer-workspace:pending"]

/** Take away the layouts kept for everyone, so nobody's tabs linger in them. */
export function forgetSharedLayouts(storage: Storage = localStorage): void {
  for (const key of SHARED_LAYOUT_KEYS) {
    try {
      storage.removeItem(serverStorageKey(key))
    } catch {
      // Blocked storage holds nothing to forget.
    }
  }
}
