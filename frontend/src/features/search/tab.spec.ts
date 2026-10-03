import { describe, expect, it } from "vitest"

import type { Hit } from "@/client"

import { EMPTY_ANSWER, reduceAnswer } from "./answer"
import type { AnswerState } from "./answer"
import type { SearchLine } from "./stream"
import { filterChoices, foundCount, kindLabel, NO_FILTERS, passes, tabGroups } from "./tab"
import { CONNECTIONS, GUIDE, hit, IN_PG, outcome, plannedCell, TYPES } from "./testing"

const NOW = Date.parse("2026-10-03T12:00:00Z")
const DAY = 24 * 60 * 60 * 1000

function table(name: string, changedDaysAgo: number | null): Hit {
  return hit(`node:c1:public.${name}:`, {
    target: {
      kind: "node",
      connector_id: "c1",
      node_id: `public.${name}`,
      parent_id: "public",
      location: "public",
      name,
      node_kind: "table",
      sub_key: null,
      ancestors: null,
      node: null,
    },
    title: name,
    facts: {
      kind: "table",
      changed_at: changedDaysAgo === null ? null : new Date(NOW - changedDaysAgo * DAY).toISOString(),
      owner: null,
      switched_off: false,
    },
    open: "rows",
  })
}

const PG_ROW = hit("connection:c1", {
  target: { kind: "connection", connector_id: "c1" },
  title: "local pg",
  facts: { kind: "postgres", changed_at: null, owner: null, switched_off: false },
  open: "catalog",
})

const PLAN: SearchLine = {
  type: "plan",
  mode: "search",
  cells: [
    plannedCell("connections/names", CONNECTIONS),
    plannedCell("connection:c1/names", IN_PG, { cost: "cheap" }),
    plannedCell("objects:guide/names", GUIDE),
    plannedCell("objects:source_types/names", TYPES),
  ],
}

function play(lines: SearchLine[]): AnswerState {
  return lines.reduce(reduceAnswer, EMPTY_ANSWER)
}

describe("the Search tab's groups", () => {
  it("keeps a place still being asked in its place, and drops one that looked and found nothing", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [PG_ROW] },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("Guide A")] },
      { type: "cell", key: "objects:source_types/names", outcome: outcome(), hits: [] },
    ])
    const groups = tabGroups(state, NO_FILTERS, NOW)
    expect(groups.map((group) => group.title)).toEqual(["Connections", "local pg", "Guide"])
    expect(groups[1]?.pending).toBe(true)
  })

  it("draws a group that found nothing when it has something to say about itself", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connection:c1/names", outcome: outcome({ status: "late", deadline_seconds: 2 }), hits: [] },
    ])
    const late = tabGroups(state, NO_FILTERS, NOW).find((group) => group.key === "connection:c1")
    expect(late?.hits).toEqual([])
    expect(late?.said.map((one) => one.said.sentence)).toEqual(["Didn't answer in 2 s"])
  })

  it("narrows by group, by connection, by kind and by when it changed", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [PG_ROW] },
      {
        type: "cell",
        key: "connection:c1/names",
        outcome: outcome(),
        hits: [table("orders", 0.5), table("users", 20), table("old", null)],
      },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("Guide A")] },
      { type: "cell", key: "objects:source_types/names", outcome: outcome(), hits: [] },
    ])
    const titles = (filters: Partial<typeof NO_FILTERS>) =>
      tabGroups(state, { ...NO_FILTERS, ...filters }, NOW).flatMap((group) => group.hits.map((one) => one.title))

    expect(titles({ group: "objects:guide" })).toEqual(["Guide A"])
    expect(titles({ connection: "c1" })).toEqual(["local pg", "orders", "users", "old"])
    expect(titles({ kind: "table" })).toEqual(["orders", "users", "old"])
    expect(titles({ changed: "day" })).toEqual(["orders"])
    expect(titles({ changed: "month" })).toEqual(["orders", "users"])
  })

  it("leaves out what does not say when it changed once a time is chosen", () => {
    expect(passes(table("old", null), { ...NO_FILTERS, changed: "year" }, NOW)).toBe(false)
    expect(passes(table("old", null), NO_FILTERS, NOW)).toBe(true)
  })

  it("offers each filter only what this answer holds", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [PG_ROW] },
      { type: "cell", key: "connection:c1/names", outcome: outcome(), hits: [table("orders", 1)] },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("Guide A")] },
      { type: "cell", key: "objects:source_types/names", outcome: outcome(), hits: [] },
    ])
    const choices = filterChoices(state)
    expect(choices.groups.map((one) => one.label)).toEqual(["Connections", "local pg", "Guide"])
    expect(choices.connections).toEqual([{ label: "local pg", value: "c1" }])
    expect(choices.kinds.map((one) => one.label)).toEqual(["Guide page", "Postgres", "Table"])
    expect(foundCount(state)).toBe(3)
  })

  it("names a kind the way a person reads it", () => {
    expect(kindLabel("saved_query")).toBe("Saved query")
    expect(kindLabel("materialized_view")).toBe("Materialized view")
  })
})
