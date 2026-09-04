import { z } from "zod"

import { parseWorkspace } from "@/shared/workspace/persist"
import { leavesOf } from "@/shared/workspace/tree"

import { panelSchema, roleOf } from "./panels"

const groupSchema = z.object({
  id: z.string().min(1),
  name: z.string().trim().min(1).max(80),
  snapshot: z.string(),
})
export type TabGroup = z.infer<typeof groupSchema>

export const groupsKey = (userId: string) => `dataplayer-tab-groups:${userId}`
export const groupWarningKey = (userId: string) => `dataplayer-tab-groups:skip-warning:${userId}`

export function validGroupSnapshot(raw: string): boolean {
  const saved = parseWorkspace(raw, panelSchema)
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
  if (!trimmed) return "Enter a group name."
  if (trimmed.length > 80) return "Use at most 80 characters."
  if (groups.some((group) => group.id !== exceptId && group.name.toLowerCase() === trimmed.toLowerCase())) {
    return "A group with this name already exists."
  }
  return ""
}
