import { describe, expect, it } from "vitest"

import { EMPTY_ANSWER, reduceAnswer } from "./answer"
import { appIcons } from "@/shared/ui/icons"

import {
  ASK_VALUE,
  ASK_OPTION,
  BY_MEANING,
  fieldOptions,
  hitOption,
  recentOptions,
  ROWS_IN_FIELD,
  SHOW_IN_CATALOG,
} from "./rows"
import type { SearchLine } from "./stream"
import { CONNECTIONS, GUIDE, hit, outcome, plannedCell } from "./testing"

const RECENT = { key: "objects:recent", title: "Recently opened", rank: 0 }

const PLAN: SearchLine = {
  type: "plan",
  mode: "typing",
  cells: [plannedCell("connections/names", CONNECTIONS), plannedCell("objects:guide/names", GUIDE)],
}

describe("the rows of the field", () => {
  it("puts the best matches first and does not repeat them in their group", () => {
    const state = [
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [hit("pg"), hit("pg2")] },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("Guide A")] },
      { type: "best", hits: [hit("pg")] },
    ].reduce((answer, line) => reduceAnswer(answer, line as SearchLine), EMPTY_ANSWER)
    expect(fieldOptions(state).map((option) => option.label)).toEqual([
      "Best matches",
      "pg",
      "Connections",
      "pg2",
      "Guide",
      "Guide A",
    ])
  })

  it("shows at most five rows of a group, and no group that found nothing", () => {
    const many = Array.from({ length: 8 }, (_, index) => hit(`pg${String(index)}`))
    const state = [
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: many },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [] },
      { type: "best", hits: [] },
    ].reduce((answer, line) => reduceAnswer(answer, line as SearchLine), EMPTY_ANSWER)
    const options = fieldOptions(state)
    expect(options.filter((option) => option.group).map((option) => option.label)).toEqual(["Connections"])
    expect(options.filter((option) => !option.group)).toHaveLength(ROWS_IN_FIELD)
  })

  it("marks the words that found a name in the name, and the words that found a body below it", () => {
    const byName = hitOption(hit("orders", { match: { field: "name", match_class: "prefix", line: null, excerpt: [{ text: "ord", hit: true }, { text: "ers", hit: false }] } }))
    expect(byName.labelRuns).toEqual([{ text: "ord", hit: true }, { text: "ers", hit: false }])
    expect(byName.descriptionRuns).toBeUndefined()

    const byBody = hitOption(hit("Redis", {
      detail: "Guide",
      match: { field: "body", match_class: "text", line: null, excerpt: [{ text: "… keys ", hit: false }, { text: "orders", hit: true }] },
    }))
    expect(byBody.labelRuns).toBeUndefined()
    expect(byBody.descriptionRuns?.map((run) => run.text).join("")).toBe("… keys orders")
  })

  it("offers Show in catalog on a node's row and on no other", () => {
    const node = hitOption(hit("node:c1:public.orders:", {
      target: {
        kind: "node", connector_id: "c1", node_id: "public.orders", parent_id: "public", location: "public",
        name: "orders", node_kind: "table", sub_key: null, ancestors: null, node: null,
      },
      open: "rows",
    }))
    expect(node).toMatchObject({ actionIcon: appIcons.myLocation, actionLabel: SHOW_IN_CATALOG })
    const page = hitOption(hit("Redis"))
    expect(page.actionIcon).toBeUndefined()
    expect(page.actionLabel).toBeUndefined()
  })

  it("offers the recent searches while the field is empty", () => {
    expect(recentOptions([])).toEqual([])
    expect(recentOptions(["orders", "users"]).map((option) => option.label)).toEqual([
      "Recent searches",
      "orders",
      "users",
    ])
  })

  it("lets each recent search and the whole group be taken out", () => {
    expect(recentOptions(["orders"]).map((option) => option.removeLabel)).toEqual([
      "Clear recent searches",
      "Remove from recent searches",
    ])
  })

  it("lets what was opened lately be taken out, and no other group", () => {
    const state = [
      { type: "plan", mode: "typing", cells: [plannedCell("objects:recent/names", RECENT), plannedCell("objects:guide/names", GUIDE)] },
      { type: "cell", key: "objects:recent/names", outcome: outcome(), hits: [hit("a")] },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("b")] },
      { type: "best", hits: [] },
    ].reduce((answer, line) => reduceAnswer(answer, line as SearchLine), EMPTY_ANSWER)
    expect(fieldOptions(state).map((option) => [option.label, option.removeLabel])).toEqual([
      ["Recently opened", "Clear recently opened"],
      ["a", "Remove from recently opened"],
      [GUIDE.title, undefined],
      ["b", undefined],
    ])
  })
})

describe("the row that asks the agent", () => {
  it("is told apart from every hit by its value, and does not repeat the words", () => {
    expect(ASK_OPTION.label).toBe("Ask the agent")
    expect(ASK_OPTION.value).toBe(ASK_VALUE)
    expect(ASK_OPTION.description).toBeUndefined()
    expect(ASK_OPTION.icon).toBe(appIcons.robot2)
  })
})

describe("a hit found by meaning", () => {
  it("says so, and marks nothing in it", () => {
    const meant = hit("billing/notes.txt", {
      title: "notes.txt",
      match: {
        field: "contents",
        match_class: "meaning",
        line: 4,
        excerpt: [{ text: "the invoices for march", hit: false }],
      },
    })

    const option = hitOption(meant)

    expect(option.label).toBe("notes.txt")
    expect(option.labelRuns).toBeUndefined()
    expect(option.descriptionRuns).toEqual([
      { text: BY_MEANING, hit: false },
      { text: " · ", hit: false },
      { text: "Line 4: ", hit: false },
      { text: "the invoices for march", hit: false },
    ])
  })

  it("names where a name found by meaning is", () => {
    const meant = hit("customers.csv", {
      detail: "files · reports",
      match: { field: "name", match_class: "meaning", line: null, excerpt: [] },
    })

    expect(hitOption(meant).descriptionRuns).toEqual([
      { text: BY_MEANING, hit: false },
      { text: " · ", hit: false },
      { text: "files · reports", hit: false },
    ])
  })
})
