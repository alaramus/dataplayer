import { describe, expect, it } from "vitest"

import type { Hit } from "@/client"

import {
  EMPTY_ANSWER,
  foundSavedQueryText,
  groupsOf,
  lateOf,
  nothingFound,
  pendingOf,
  reduceAnswer,
  reduceFollow,
  settleFollow,
  STOPPED_BEFORE_ANSWER,
  stopPending,
  withoutHits,
} from "./answer"
import type { AnswerState } from "./answer"
import { saidOf } from "./outcomes"
import type { SearchLine } from "./stream"
import { CONNECTIONS, GUIDE, hit, IN_PG, outcome, plannedCell, TYPES } from "./testing"

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

function play(lines: SearchLine[], start: AnswerState = EMPTY_ANSWER): AnswerState {
  return lines.reduce(reduceAnswer, start)
}

describe("an answer with rows taken out", () => {
  it("leaves them out of the best matches and of every cell, and is itself with none", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [hit("a"), hit("b")] },
      { type: "best", hits: [hit("a")] },
    ])
    expect(withoutHits(state, new Set())).toBe(state)
    const left = withoutHits(state, new Set(["a"]))
    expect(left.best).toEqual([])
    expect(left.cells.flatMap((cell) => cell.hits.map((one) => one.key))).toEqual(["b"])
  })
})

describe("an answer, line by line", () => {
  it("knows every cell and every group from the plan, all of them pending", () => {
    const state = play([PLAN])
    expect(pendingOf(state)).toHaveLength(4)
    expect(groupsOf(state).map((group) => group.title)).toEqual([
      "Connections",
      "local pg",
      "Guide",
      "Source types",
    ])
    expect(groupsOf(state).every((group) => group.pending)).toBe(true)
  })

  it("fills a late cell into its own place, moving nothing drawn before it", () => {
    const early = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [hit("pg")] },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("Guide A"), hit("Guide B")] },
      { type: "cell", key: "objects:source_types/names", outcome: outcome(), hits: [] },
    ])
    const before = groupsOf(early).flatMap((group) => group.hits.map((one) => one.key))
    const late = reduceAnswer(early, {
      type: "cell",
      key: "connection:c1/names",
      outcome: outcome(),
      hits: [hit("orders")],
    })
    const after = groupsOf(late)
    expect(after.map((group) => group.title)).toEqual(["Connections", "local pg", "Guide", "Source types"])
    expect(after.flatMap((group) => group.hits.map((one) => one.key)).filter((key) => key !== "orders"))
      .toEqual(before)
    expect(after[1]?.hits.map((one) => one.key)).toEqual(["orders"])
  })

  it("keeps the best matches as they were first sent", () => {
    const state = play([
      PLAN,
      { type: "best", hits: [hit("pg")] },
      { type: "best", hits: [hit("other")] },
    ])
    expect(state.best?.map((one) => one.key)).toEqual(["pg"])
  })

  it("does not repeat a best match below, where it was found", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [hit("pg"), hit("pg2")] },
      { type: "best", hits: [hit("pg")] },
    ])
    const connections = groupsOf(state, new Set(["pg"]))[0]
    expect(connections?.hits.map((one) => one.key)).toEqual(["pg2"])
  })

  it("draws a thing found twice once, where it was found first", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome(), hits: [hit("same")] },
      { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("same")] },
    ])
    expect(groupsOf(state).map((group) => group.hits.length)).toEqual([1, 0, 0, 0])
  })

  it("counts the cells that did not answer in time", () => {
    const state = play([
      PLAN,
      { type: "cell", key: "connection:c1/names", outcome: outcome({ status: "late", deadline_seconds: 0.4 }), hits: [] },
    ])
    expect(lateOf(state).map((cell) => cell.planned.key)).toEqual(["connection:c1/names"])
  })

  it("says nothing was found only when the end line says so", () => {
    const stopped = play([
      PLAN,
      { type: "cell", key: "connections/names", outcome: outcome({ status: "stopped" }), hits: [] },
      { type: "end", nothing_found: false, asked: 4, superseded: false },
    ])
    expect(nothingFound(stopped)).toBe(false)
    const empty = play([
      PLAN,
      ...PLAN.cells.map((cell) => ({ type: "cell" as const, key: cell.key, outcome: outcome(), hits: [] })),
      { type: "end", nothing_found: true, asked: 4, superseded: false },
    ])
    expect(nothingFound(empty)).toBe(true)
  })

  it("ignores a line about a cell it was never told of", () => {
    const state = play([PLAN, { type: "cell", key: "nowhere/names", outcome: outcome(), hits: [hit("x")] }])
    expect(groupsOf(state).flatMap((group) => group.hits)).toEqual([])
  })
})

describe("a follow-up folded into the answer", () => {
  const answered = play([
    PLAN,
    { type: "cell", key: "connections/names", outcome: outcome(), hits: [hit("pg")] },
    { type: "cell", key: "connection:c1/names", outcome: outcome({ status: "late" }), hits: [] },
    { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("Guide A")] },
    { type: "cell", key: "objects:source_types/names", outcome: outcome(), hits: [] },
    { type: "best", hits: [] },
    { type: "end", nothing_found: false, asked: 4, superseded: false },
  ])

  it("puts the cell asked again back to pending in its place, the rest as they were", () => {
    const asked = reduceFollow(answered, {
      type: "plan",
      mode: "search",
      cells: [plannedCell("connection:c1/names", IN_PG)],
    })
    expect(pendingOf(asked).map((cell) => cell.planned.key)).toEqual(["connection:c1/names"])
    expect(groupsOf(asked).map((group) => group.title)).toEqual(groupsOf(answered).map((group) => group.title))
  })

  it("fills the answer of the cell asked again, and takes no best or end from it", () => {
    const lines: SearchLine[] = [
      { type: "plan", mode: "search", cells: [plannedCell("connection:c1/names", IN_PG)] },
      { type: "cell", key: "connection:c1/names", outcome: outcome(), hits: [hit("orders")] },
      { type: "best", hits: [hit("orders")] },
      { type: "end", nothing_found: false, asked: 1, superseded: false },
    ]
    const state = lines.reduce(reduceFollow, answered)
    expect(groupsOf(state)[1]?.hits.map((one) => one.key)).toEqual(["orders"])
    expect(state.best).toEqual([])
    expect(state.end?.asked).toBe(4)
  })

  it("puts back what a cell said when its follow-up never answered", () => {
    const asked = reduceFollow(answered, {
      type: "plan",
      mode: "search",
      cells: [plannedCell("connection:c1/names", IN_PG)],
    })
    const settled = settleFollow(answered, asked, new Set(["connection:c1/names"]))
    expect(pendingOf(settled)).toEqual([])
    expect(lateOf(settled)).toHaveLength(1)
  })

  it("puts back only the cells it asked, and drops a place it added", () => {
    const asked = reduceFollow(answered, {
      type: "plan",
      mode: "search",
      cells: [
        plannedCell("connection:c1/names", IN_PG),
        plannedCell("connection:c2/names", { ...IN_PG, key: "connection:c2", title: "other" }),
      ],
    })
    // A newer follow-up has put another cell to pending meanwhile.
    const other = reduceFollow(asked, {
      type: "plan",
      mode: "search",
      cells: [plannedCell("objects:guide/names", GUIDE)],
    })
    const settled = settleFollow(answered, other, new Set(["connection:c1/names", "connection:c2/names"]))
    expect(pendingOf(settled).map((cell) => cell.planned.key)).toEqual(["objects:guide/names"])
    expect(settled.cells.map((cell) => cell.planned.key)).not.toContain("connection:c2/names")
    expect(lateOf(settled)).toHaveLength(1)
  })

  it("says a cell stopped before it answered, and offers to ask it again", () => {
    const asked = reduceFollow(answered, {
      type: "plan",
      mode: "search",
      cells: [plannedCell("connection:c1/names", IN_PG)],
    })
    const stopped = stopPending(asked)
    expect(pendingOf(stopped)).toEqual([])
    const cell = stopped.cells.find((one) => one.planned.key === "connection:c1/names")
    expect(cell?.outcome?.message).toBe(STOPPED_BEFORE_ANSWER)
    expect(cell && cell.outcome ? saidOf(cell.outcome, cell.planned)?.gesture?.kind : null).toBe("retry")
    expect(nothingFound(stopped)).toBe(false)
  })

  it("says nothing was found no longer once a follow-up found something", () => {
    const empty = play([
      PLAN,
      ...PLAN.cells.map((cell) => ({ type: "cell" as const, key: cell.key, outcome: outcome(), hits: [] })),
      { type: "end", nothing_found: true, asked: 4, superseded: false },
    ])
    const found = reduceFollow(empty, {
      type: "cell",
      key: "objects:guide/names",
      outcome: outcome(),
      hits: [hit("Guide A")],
    })
    expect(nothingFound(found)).toBe(false)
  })
})

describe("words that found a saved query's text", () => {
  it("are told apart from words that found its title", () => {
    const body = hit("q1", {
      target: { kind: "object", object_type: "saved_query", object_id: "q1" },
      match: { field: "contents", match_class: "text", line: null, excerpt: [] },
    })
    const title = hit("q2", {
      target: { kind: "object", object_type: "saved_query", object_id: "q2" },
      match: { field: "name", match_class: "prefix", line: null, excerpt: [] },
    })
    const library = {
      key: "objects:saved_queries",
      title: "Favorites",
      rank: 100100,
    }
    const plan: SearchLine = {
      type: "plan",
      mode: "search",
      cells: [
        plannedCell("objects:saved_queries/names", library),
        plannedCell("objects:saved_queries/contents", library, { cost: "costly" }),
      ],
    }
    const answer = (titles: Hit[], bodies: Hit[]) =>
      play([
        plan,
        { type: "cell", key: "objects:saved_queries/names", outcome: outcome(), hits: titles },
        { type: "cell", key: "objects:saved_queries/contents", outcome: outcome(), hits: bodies },
      ])
    expect(foundSavedQueryText(answer([title], []))).toBe(false)
    expect(foundSavedQueryText(answer([title], [body]))).toBe(true)
    expect(foundSavedQueryText(answer([], [{ ...body, match: { ...body.match, field: "body" } }]))).toBe(true)
  })

  it("are told apart even when the query's title matched as well, and it is drawn once", () => {
    const library = { key: "objects:saved_queries", title: "Favorites", rank: 100100 }
    const target = { kind: "object" as const, object_type: "saved_query" as const, object_id: "q1" }
    const byTitle = hit("object:saved_query:q1", {
      target,
      match: { field: "name", match_class: "prefix", line: null, excerpt: [] },
    })
    const byBody = hit("object:saved_query:q1", {
      target,
      match: { field: "body", match_class: "text", line: null, excerpt: [] },
    })
    const state = play([
      {
        type: "plan",
        mode: "search",
        cells: [
          plannedCell("objects:saved_queries/names", library),
          plannedCell("objects:saved_queries/contents", library, { cost: "costly" }),
        ],
      },
      { type: "cell", key: "objects:saved_queries/names", outcome: outcome(), hits: [byTitle] },
      { type: "cell", key: "objects:saved_queries/contents", outcome: outcome(), hits: [byBody] },
    ])
    expect(groupsOf(state)[0]?.hits).toEqual([byTitle])
    expect(foundSavedQueryText(state)).toBe(true)
  })
})
