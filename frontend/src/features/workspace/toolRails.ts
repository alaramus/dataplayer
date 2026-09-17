import { ref } from "vue"
import type { Ref } from "vue"

/**
 * Which tool blocks live on which side rail.
 *
 * PyCharm-style: every block is icon-only and can be dragged within its rail
 * or across to any other one. Each side is split into top and bottom halves,
 * so there are four rails. The arrangement is kept in localStorage so a
 * reload keeps the layout the user arranged.
 */
export type ToolRailZone = "left-top" | "left-bottom" | "right-top" | "right-bottom"

const ZONES: readonly ToolRailZone[] = ["left-top", "left-bottom", "right-top", "right-bottom"]

/**
 * Static blocks plus the groups section: the save button and the saved-groups
 * list button are blocks of their own, so each drags separately.
 */
export const STATIC_BLOCKS = ["spaces", "queries", "services"] as const
export const GROUPS_SAVE = "groups-save"
export const GROUPS_LIST = "groups-list"
function isKnown(id: string): boolean {
  return (STATIC_BLOCKS as readonly string[]).includes(id) || id === GROUPS_SAVE || id === GROUPS_LIST
}

const STORAGE_KEY = "dataplayer-tool-rails"

const DEFAULTS: Record<ToolRailZone, readonly string[]> = {
  "left-top": [...STATIC_BLOCKS.slice(0, 2)],
  "left-bottom": [...STATIC_BLOCKS.slice(2)],
  "right-top": [GROUPS_SAVE, GROUPS_LIST],
  "right-bottom": [],
}

/** Stored ids, minus what is not a block, with every block kept once. */
function clean(list: unknown): string[] {
  if (!Array.isArray(list)) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of list) {
    const id = String(raw)
    if (!isKnown(id) || seen.has(id)) continue
    seen.add(id)
    out.push(id)
  }
  return out
}

type Zones = Record<ToolRailZone, string[]>

function read(): Zones {
  const fresh = (): Zones => ({
    "left-top": [...DEFAULTS["left-top"]],
    "left-bottom": [...DEFAULTS["left-bottom"]],
    "right-top": [...DEFAULTS["right-top"]],
    "right-bottom": [...DEFAULTS["right-bottom"]],
  })
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw !== null) {
      const parsed = JSON.parse(raw) as Record<string, unknown>
      const zones = fresh()
      for (const zone of ZONES) zones[zone] = clean(parsed[zone])
      // A block the store does not place would be lost to the user: anything
      // missing takes its default seat, with the groups list beside the save
      // button wherever that stands.
      const placed = new Set(ZONES.flatMap((zone) => zones[zone]))
      for (const id of STATIC_BLOCKS) {
        if (!placed.has(id)) {
          zones["left-top"].push(id)
          placed.add(id)
        }
      }
      for (const id of [GROUPS_SAVE, GROUPS_LIST]) {
        if (placed.has(id)) continue
        const host: ToolRailZone =
          ZONES.find((zone) => zones[zone].includes(GROUPS_SAVE)) ?? "right-top"
        if (id === GROUPS_LIST) {
          const at = zones[host].indexOf(GROUPS_SAVE)
          zones[host].splice(at < 0 ? zones[host].length : at + 1, 0, id)
        } else {
          zones[host].push(id)
        }
        placed.add(id)
      }
      return zones
    }
  } catch {
    // An arrangement that cannot be read falls back to the default one.
  }
  return fresh()
}

const stored = read()
const rails: Record<ToolRailZone, Ref<string[]>> = {
  "left-top": ref<string[]>(stored["left-top"]),
  "left-bottom": ref<string[]>(stored["left-bottom"]),
  "right-top": ref<string[]>(stored["right-top"]),
  "right-bottom": ref<string[]>(stored["right-bottom"]),
}

function persist() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        "left-top": rails["left-top"].value,
        "left-bottom": rails["left-bottom"].value,
        "right-top": rails["right-top"].value,
        "right-bottom": rails["right-bottom"].value,
      })
    )
  } catch {
    // Losing the arrangement to a full or blocked storage loses nothing else.
  }
}

/** A zone always holds a rail: the record is built with every zone. */
function railOf(zone: ToolRailZone) {
  const found = rails[zone]
  if (found === undefined) throw new Error(`Unknown tool rail: ${zone}`)
  return found
}

export function useToolRails() {
  function placeBlock(id: string, zone: ToolRailZone, index: number) {
    for (const other of ZONES) {
      if (other === zone) continue
      const rail = railOf(other)
      rail.value = rail.value.filter((block) => block !== id)
    }
    const current = railOf(zone)
    const without = current.value.filter((block) => block !== id)
    const clamped = Math.max(0, Math.min(index, without.length))
    current.value = [...without.slice(0, clamped), id, ...without.slice(clamped)]
    persist()
  }

  function resetRails() {
    for (const zone of ZONES) railOf(zone).value = [...DEFAULTS[zone]]
    persist()
  }

  return {
    blocksOf: railOf,
    placeBlock,
    resetRails,
  }
}
