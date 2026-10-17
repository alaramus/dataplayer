import { z } from "zod"
import { serverStorageKey } from "@/shared/servers/context"
import { t } from "@/shared/i18n"
import type { Space } from "@/stores/space"

import { parseWorkspace } from "@/shared/workspace/persist"
import { leavesOf } from "@/shared/workspace/tree"

import { isRetiredPanel, panelSchema, roleOf } from "./panels"

/** The longest name a group may have, here and in the dialog. */
export const NAME_MAX = 80

const groupSchema = z.object({
  id: z.string().min(1),
  name: z.string().trim().min(1).max(NAME_MAX),
  snapshot: z.string(),
})
export type TabGroup = z.infer<typeof groupSchema>

/**
 * Why tab groups cannot be used in this space, or nothing.
 *
 * A group is the tabs of Data. Its buttons stand on a rail every space shows,
 * so elsewhere they are greyed with this rather than saving or opening a
 * layout nobody is looking at.
 */
export function groupsUnavailableIn(space: Space): string | null {
  return space === "data" ? null : t("workspace.groups.unavailable")
}

export const groupsKey = (userId: string) => serverStorageKey(`dataplayer-tab-groups:${userId}`)
export const groupWarningKey = (userId: string) => serverStorageKey(`dataplayer-tab-groups:skip-warning:${userId}`)

export function validGroupSnapshot(raw: string): boolean {
  const saved = parseWorkspace(raw, panelSchema, isRetiredPanel)
  if (saved === null) return false
  const panels = new Map(saved.panels.map((panel) => [panel.id, panel]))
  if (panels.get("connectors")?.kind !== "connectors") return false
  const leaves = leavesOf(saved.tree)
  if (!["sources", "navigate", "work"].every((role) =>
    leaves.some((leaf) => leaf.pinned === true && leaf.accepts === role)
  )) return false
  return leaves.every((leaf) => leaf.panels.every((id) => {
    const panel = panels.get(id)
    return panel !== undefined && leaf.accepts === roleOf(panel)
  }))
}

export function parseGroups(raw: string | null): TabGroup[] | null {
  if (raw === null) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    const result = z.object({ version: z.literal(1), groups: z.array(groupSchema) }).safeParse(parsed)
    if (!result.success) return null
    const groups = result.data.groups
    if (new Set(groups.map((group) => group.id)).size !== groups.length) return null
    if (new Set(groups.map((group) => group.name.toLowerCase())).size !== groups.length) return null
    return groups.every((group) => validGroupSnapshot(group.snapshot)) ? groups : null
  } catch {
    return null
  }
}

export function serializeGroups(groups: readonly TabGroup[]): string {
  return JSON.stringify({ version: 1, groups })
}

export function groupNameProblem(name: string, groups: readonly TabGroup[], exceptId?: string): string {
  const trimmed = name.trim()
  if (!trimmed) return t("workspace.groups.name_required")
  if (trimmed.length > NAME_MAX) return t("workspace.groups.name_too_long", { max: NAME_MAX })
  if (groups.some((group) => group.id !== exceptId && group.name.toLowerCase() === trimmed.toLowerCase())) {
    return t("workspace.groups.name_taken")
  }
  return ""
}

/**
 * The first name of that family which is free.
 *
 * Free by the rule `groupNameProblem` enforces — case and surrounding spaces
 * do not make a second name — so the dialog opens on something Save accepts
 * rather than on a name it is about to refuse.
 */
export function suggestedGroupName(groups: readonly TabGroup[]): string {
  // What the dialog offers before anybody has typed a name of their own.
  const base = t("workspace.groups.default_name")
  const taken = new Set(groups.map((group) => group.name.trim().toLowerCase()))
  const candidates = [
    base,
    ...groups.map((_, index) => `${base}(${index + 1})`),
  ]
  // One candidate more than there are groups, so one of them is always free;
  // the fallback is there for the type and for nothing else.
  return candidates.find((candidate) => !taken.has(candidate)) ?? base
}
