import { z } from "zod"

import { serverStorageKey } from "@/shared/servers/context"

/**
 * Which groupings of a connection were ticked, kept for the next visit.
 *
 * The catalog opens on what the source prefers, or on all the real groupings
 * while there are few — a rule about a connection nobody has an opinion about
 * yet. Once somebody has an opinion, it is theirs: turning a schema off and
 * finding it back after a reload is the application overruling them.
 *
 * The browser's, keyed by server and connection, the way a grid remembers its
 * columns. Not the server's: which schemas one person is looking at on one
 * machine is not a fact about the connection.
 */
const VERSION = 1

const storedSchema = z.strictObject({
  version: z.literal(VERSION),
  groups: z.array(z.string()),
})

function keyOf(connectorId: string): string {
  return serverStorageKey(`dataplayer:catalog-groups:${JSON.stringify([connectorId])}`)
}

/** What was ticked last time, or nothing when nobody has said. */
export function rememberedGroups(connectorId: string): string[] | undefined {
  let raw: string | null = null
  try {
    raw = localStorage.getItem(keyOf(connectorId))
  } catch {
    // Unavailable or blocked storage is the same as never having been told.
    return undefined
  }
  if (raw === null) return undefined
  try {
    const parsed = storedSchema.safeParse(JSON.parse(raw) as unknown)
    return parsed.success ? parsed.data.groups : undefined
  } catch {
    return undefined
  }
}

/** Remember an explicit choice. Only a choice — never a default filled in. */
export function rememberGroups(connectorId: string, groups: string[]): void {
  try {
    localStorage.setItem(
      keyOf(connectorId),
      JSON.stringify({ version: VERSION, groups })
    )
  } catch {
    // Keep this session usable when browser storage is full or blocked.
  }
}
