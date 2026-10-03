import { z } from "zod"

import type { Hit, RecentTarget } from "@/client"
import { serverStorageKey } from "@/shared/servers/context"

/** How many things opened from the search are kept and sent (S6). */
export const RECENTLY_OPENED_LIMIT = 50

const KEY = "dp.search.opened"

// The server's own bounds (app/search/models.py): a target past one would
// refuse the whole search it travels in.
const MAX_NODE_ID = 4096
const MAX_OBJECT_ID = 500
const MAX_NODE_KIND = 64
const MAX_NODE_NAME = 1000

type ObjectType = NonNullable<RecentTarget["object_type"]>

/** A record over the generated union, so a type the server adds is kept only once it is named here. */
const OBJECT_TYPES: Record<ObjectType, true> = {
  saved_query: true,
  pipeline: true,
  dashboard: true,
  conversation: true,
  quick_chat: true,
  project: true,
  service: true,
  ssh_key: true,
  guide_page: true,
  source_type: true,
  tab: true,
  tab_group: true,
}

const objectType = z
  .string()
  .refine((value): value is ObjectType => Object.hasOwn(OBJECT_TYPES, value))

const targetSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("connection"), connector_id: z.string().min(1) }),
  z.object({
    kind: z.literal("node"),
    connector_id: z.string().min(1),
    node_id: z.string().min(1).max(MAX_NODE_ID),
    name: z.string().transform((value) => value.slice(0, MAX_NODE_NAME)),
    node_kind: z.string().min(1).max(MAX_NODE_KIND),
  }),
  z.object({
    kind: z.literal("object"),
    object_type: objectType,
    object_id: z.string().min(1).max(MAX_OBJECT_ID),
  }),
])

/** One string per thing, as the server keys a target. */
export function openedKey(target: RecentTarget): string {
  switch (target.kind) {
    case "connection":
      return `connection:${target.connector_id ?? ""}`
    case "node":
      return `node:${target.connector_id ?? ""}:${target.node_id ?? ""}`
    case "object":
      return `object:${target.object_type ?? ""}:${target.object_id ?? ""}`
  }
}

function valid(value: unknown): RecentTarget | null {
  const parsed = targetSchema.safeParse(value)
  return parsed.success ? parsed.data : null
}

/** What a hit points at, as it is kept: the target only, never what was found in it. */
export function openedTarget(hit: Hit): RecentTarget | null {
  const target = hit.target
  switch (target.kind) {
    case "connection":
      return valid({ kind: "connection", connector_id: target.connector_id })
    case "node":
      return valid({
        kind: "node",
        connector_id: target.connector_id,
        node_id: target.node_id,
        name: target.name,
        node_kind: target.node_kind,
      })
    case "object":
      return valid({ kind: "object", object_type: target.object_type, object_id: target.object_id })
  }
}

/**
 * What was kept, newest first, once each. Read defensively, entry by entry:
 * a damaged entry costs itself and nothing else.
 */
export function parseOpened(raw: string | null): RecentTarget[] {
  if (raw === null) return []
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  const targets: RecentTarget[] = []
  for (const item of value) {
    const target = valid(item)
    if (target === null) continue
    const key = openedKey(target)
    if (seen.has(key)) continue
    seen.add(key)
    targets.push(target)
  }
  return targets.slice(0, RECENTLY_OPENED_LIMIT)
}

/** The list with this target first, once. */
export function withOpened(targets: readonly RecentTarget[], target: RecentTarget): RecentTarget[] {
  const key = openedKey(target)
  return [target, ...targets.filter((one) => openedKey(one) !== key)].slice(0, RECENTLY_OPENED_LIMIT)
}

// Per person as well as per server (D99): local storage outlives a sign-in,
// and what one person opened is not offered to the next.
function storageKey(userId: string): string {
  return serverStorageKey(`${KEY}:${userId}`)
}

/** What this person last opened from the search, newest first. */
export function readOpened(userId: string | null | undefined): RecentTarget[] {
  if (!userId) return []
  try {
    return parseOpened(localStorage.getItem(storageKey(userId)))
  } catch {
    return []
  }
}

/** A hit opened from the search, kept first. */
export function rememberOpened(userId: string | null | undefined, hit: Hit): void {
  if (!userId) return
  const target = openedTarget(hit)
  if (target === null) return
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(withOpened(readOpened(userId), target)))
  } catch {
    // No storage left: the hint is lost, the search still answers.
  }
}

/** Emptied on sign-out, as the recent searches are (D205). */
export function forgetOpened(userId: string | null | undefined): void {
  if (!userId) return
  try {
    localStorage.removeItem(storageKey(userId))
  } catch {
    // Nothing was kept.
  }
}
