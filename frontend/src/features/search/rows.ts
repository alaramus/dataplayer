import type { Hit } from "@/client"
import { iconOf } from "@/features/catalog/nodes"
import { adapterIcon } from "@/features/connectors/adapters"
import { appIcons } from "@/shared/ui/icons"
import type { SelectOption, TextRun } from "@/shared/ui"

import { groupsOf } from "./answer"
import type { AnswerState } from "./answer"
import { showsInCatalog } from "./intents"
import { OBJECT_ICONS } from "./kinds"

/** What a hit is drawn with: its source's icon, its node's, or its kind's. */
export function hitIcon(hit: Hit): string {
  switch (hit.target.kind) {
    case "connection":
      return adapterIcon(hit.facts.kind)
    case "node":
      return hit.target.node === null ? appIcons.description : iconOf(hit.target.node)
    case "object":
      return hit.target.object_type === "source_type"
        ? adapterIcon(hit.target.object_id)
        : OBJECT_ICONS[hit.target.object_type]
  }
}

/** What a node's row offers beside opening it (D205). */
export const SHOW_IN_CATALOG = "Show in catalog"

/**
 * A hit as a row: its title, and on the second line what it is — or, when it
 * was found by something other than its name, the words that found it.
 * Segments become runs of text, the hit marked, never HTML (D198). A node's
 * row carries Show in catalog as its own action.
 */
export function hitOption(hit: Hit): SelectOption {
  const runs: TextRun[] = hit.match.excerpt.map((segment) => ({ text: segment.text, hit: segment.hit }))
  const byName = hit.match.field === "name"
  return {
    label: hit.title,
    value: hit.key,
    icon: hitIcon(hit),
    ...(byName && runs.length > 0 ? { labelRuns: runs } : {}),
    ...(!byName && runs.length > 0
      ? { descriptionRuns: runs }
      : hit.detail
        ? { description: hit.detail }
        : {}),
    ...(showsInCatalog(hit) ? { actionIcon: appIcons.myLocation, actionLabel: SHOW_IN_CATALOG } : {}),
  }
}

/** The value of the row that offers a scope (D205). */
export const SCOPE_VALUE = "scope:"

/** How many rows a group shows in the field; the server sends no more (D200). */
export const ROWS_IN_FIELD = 5

/**
 * The rows of the field: the best matches first, then each group in its
 * fixed place with what it found, the best not repeated below (D202).
 * Groups with nothing in them are not drawn.
 */
export function fieldOptions(state: AnswerState): SelectOption[] {
  const best = state.best ?? []
  const options: SelectOption[] = []
  if (best.length > 0) {
    options.push({ label: "Best matches", value: "group:best", group: true })
    options.push(...best.map(hitOption))
  }
  for (const group of groupsOf(state, new Set(best.map((hit) => hit.key)))) {
    if (group.hits.length === 0) continue
    options.push({ label: group.title, value: `group:${group.key}`, group: true })
    options.push(...group.hits.slice(0, ROWS_IN_FIELD).map(hitOption))
  }
  return options
}

/** Recent searches, offered while the field is empty (D205). */
export function recentOptions(entries: readonly string[]): SelectOption[] {
  if (entries.length === 0) return []
  return [
    { label: "Recent searches", value: "group:recent", group: true },
    ...entries.map((words) => ({ label: words, value: `recent:${words}`, icon: appIcons.history })),
  ]
}
