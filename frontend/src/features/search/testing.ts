import type { Hit, Outcome, PlannedCell } from "@/client"

/**
 * Lines and hits as the server writes them, for the tests of what draws them.
 *
 * Every field present, as the generated types say a line always has them.
 */
export function plannedCell(
  key: string,
  group: { key: string; title: string; rank: number },
  over: Partial<PlannedCell> = {}
): PlannedCell {
  const [where = "objects:guide"] = key.split("/")
  const place = where.startsWith("connection:")
    ? { kind: "connection" as const, connector_id: where.split(":")[1] ?? "", node_id: null }
    : where === "connections"
      ? { kind: "connections" as const }
      : { kind: "objects" as const, provider: (where.split(":")[1] ?? "guide") as "guide" }
  return {
    key,
    cell: { place, field: "names" },
    group,
    cost: "instant",
    way: "live",
    connector_id: place.kind === "connection" ? place.connector_id : null,
    contents: false,
    ...over,
  }
}

export function outcome(over: Partial<Outcome> = {}): Outcome {
  return {
    way: "live",
    status: "complete",
    reason: null,
    notice: null,
    error_kind: null,
    message: null,
    more: false,
    as_of: null,
    deadline_seconds: null,
    since: null,
    owned: false,
    ...over,
  }
}

export function hit(key: string, over: Partial<Hit> = {}): Hit {
  return {
    key,
    target: { kind: "object", object_type: "guide_page", object_id: key },
    title: key,
    detail: null,
    facts: { kind: "guide_page", changed_at: null, owner: null, switched_off: false },
    match: { field: "name", match_class: "substring", line: null, excerpt: [{ text: key, hit: true }] },
    access: null,
    open: "guide_page",
    via: "live",
    as_of: null,
    ...over,
  }
}

export const CONNECTIONS = { key: "connections", title: "Connections", rank: 10 }
export const GUIDE = { key: "objects:guide", title: "Guide", rank: 100600 }
export const TYPES = { key: "objects:source_types", title: "Source types", rank: 100700 }
export const IN_PG = { key: "connection:c1", title: "local pg", rank: 1000 }
