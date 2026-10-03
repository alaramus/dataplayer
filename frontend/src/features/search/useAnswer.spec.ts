import { flushPromises } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { effectScope, nextTick, ref } from "vue"

import type { SearchRequest } from "@/client"

import { pendingOf, STOPPED_BEFORE_ANSWER } from "./answer"
import { useFieldAnswer, useTabAnswer } from "./useAnswer"
import type { Ask, FieldContext } from "./useAnswer"
import type { SearchLine } from "./stream"
import { GUIDE, hit, IN_PG, outcome, plannedCell } from "./testing"

const PLAN: SearchLine = { type: "plan", mode: "typing", cells: [plannedCell("objects:guide/names", GUIDE)] }

/** An ask that answers whatever lines it is given, and remembers every request and signal. */
function scripted(lines: SearchLine[] | ((request: SearchRequest) => SearchLine[])) {
  const asked: { request: SearchRequest; signal: AbortSignal }[] = []
  const ask: Ask = (request, signal) => {
    asked.push({ request, signal })
    const answer = typeof lines === "function" ? lines(request) : lines
    return (async function* () {
      for (const line of answer) {
        await Promise.resolve()
        if (signal.aborted) return
        yield line
      }
    })()
  }
  return { ask, asked }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe("the field's answer", () => {
  function field(ask: Ask, around: () => FieldContext = () => ({ context: ["c1"], only: null })) {
    const words = ref("")
    const scope = effectScope()
    const answer = scope.run(() => useFieldAnswer(words, around, ask))!
    return { words, answer, scope }
  }

  it("asks once typing pauses for 150 ms, in mode typing on the field's lane", async () => {
    const { ask, asked } = scripted([PLAN, { type: "best", hits: [] }, { type: "end", nothing_found: false, asked: 1, superseded: false }])
    const { words } = field(ask)
    for (const typed of ["o", "or", "ord", "orde"]) {
      words.value = typed
      await nextTick()
      vi.advanceTimersByTime(100)
    }
    expect(asked).toHaveLength(0)
    vi.advanceTimersByTime(50)
    await flushPromises()
    expect(asked.map((one) => one.request)).toEqual([
      { words: "orde", mode: "typing", lane: "field", context: ["c1"] },
    ])
  })

  it("does not ask for fewer than two characters, and forgets the last answer", async () => {
    const { ask, asked } = scripted([PLAN, { type: "best", hits: [] }])
    const { words, answer } = field(ask)
    words.value = "or"
    await nextTick()
    vi.advanceTimersByTime(150)
    await flushPromises()
    expect(answer.drawn.value).not.toBeNull()
    words.value = "o"
    await nextTick()
    vi.advanceTimersByTime(150)
    await flushPromises()
    expect(asked).toHaveLength(1)
    expect(answer.drawn.value).toBeNull()
  })

  it("aborts the ask before when the words change", async () => {
    const { ask, asked } = scripted([PLAN, { type: "best", hits: [] }])
    const { words } = field(ask)
    words.value = "or"
    await nextTick()
    vi.advanceTimersByTime(150)
    words.value = "ord"
    await nextTick()
    expect(asked[0]?.signal.aborted).toBe(true)
  })

  it("draws an answer whole, once its best matches are in", async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => { release = resolve })
    const ask: Ask = (_, signal) =>
      (async function* () {
        yield PLAN
        yield { type: "cell", key: "objects:guide/names", outcome: outcome(), hits: [hit("Guide A")] } as SearchLine
        await gate
        if (signal.aborted) return
        yield { type: "best", hits: [] } as SearchLine
      })()
    const { words, answer } = field(ask)
    words.value = "gu"
    await nextTick()
    vi.advanceTimersByTime(150)
    await flushPromises()
    expect(answer.live.value.cells[0]?.hits).toHaveLength(1)
    expect(answer.drawn.value).toBeNull()
    release()
    await flushPromises()
    expect(answer.drawn.value?.cells[0]?.hits).toHaveLength(1)
  })

  it("names a scope it was given and the connections in context", async () => {
    const { ask, asked } = scripted([PLAN])
    const only = [{ kind: "connection" as const, connector_id: "c1", node_id: "public" }]
    const { words } = field(ask, () => ({ context: ["c1", "c2"], only }))
    words.value = "orders"
    await nextTick()
    vi.advanceTimersByTime(150)
    await flushPromises()
    expect(asked[0]?.request).toEqual({ words: "orders", mode: "typing", lane: "field", context: ["c1", "c2"], only })
  })

  it("stops asking when its owner goes", async () => {
    const { ask, asked } = scripted([PLAN])
    const { words, scope } = field(ask)
    words.value = "orders"
    await nextTick()
    scope.stop()
    vi.advanceTimersByTime(150)
    await flushPromises()
    expect(asked).toHaveLength(0)
  })
})

describe("the tab's answer", () => {
  it("ends the follow-ups of a search when a new search starts", async () => {
    const never: Ask = (_, signal) =>
      (async function* () {
        yield PLAN
        await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve()))
      })()
    const signals: AbortSignal[] = []
    const ask: Ask = (request, signal) => {
      signals.push(signal)
      return never(request, signal)
    }
    const scope = effectScope()
    const tab = scope.run(() => useTabAnswer(ask))!
    void tab.search({ words: "orders", mode: "search", lane: "tab" })
    void tab.follow({ words: "orders", mode: "search", lane: "follow", only: [] })
    await flushPromises()
    void tab.search({ words: "users", mode: "search", lane: "tab" })
    await flushPromises()
    expect(signals.slice(0, 2).every((signal) => signal.aborted)).toBe(true)
    expect(signals[2]?.aborted).toBe(false)
    scope.stop()
    expect(signals[2]?.aborted).toBe(true)
  })

  it("asks one follow-up at a time, the older one's places as they were before it", async () => {
    const late = plannedCell("connection:c1/names", IN_PG)
    const down = plannedCell("connection:c2/names", { ...IN_PG, key: "connection:c2", title: "other" })
    const answer: SearchLine[] = [
      { type: "plan", mode: "search", cells: [late, down] },
      { type: "cell", key: late.key, outcome: outcome({ status: "late" }), hits: [] },
      { type: "cell", key: down.key, outcome: outcome({ status: "skipped", reason: "unreachable" }), hits: [] },
      { type: "end", nothing_found: false, asked: 1, superseded: false },
    ]
    const signals: AbortSignal[] = []
    const ask: Ask = (request, signal) => {
      signals.push(signal)
      if (request.lane === "tab") return scripted(answer).ask(request, signal)
      const cell = request.only?.[0]?.kind === "connection" && request.only[0].connector_id === "c1" ? late : down
      return (async function* () {
        yield { type: "plan", mode: "search", cells: [cell] } as SearchLine
        await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve()))
      })()
    }
    const scope = effectScope()
    const tab = scope.run(() => useTabAnswer(ask))!
    await tab.search({ words: "orders", mode: "search", lane: "tab" })
    void tab.follow({ words: "orders", mode: "search", lane: "follow", only: [late.cell.place], insist: true })
    await flushPromises()
    expect(pendingOf(tab.state.value).map((cell) => cell.planned.key)).toEqual([late.key])
    void tab.follow({ words: "orders", mode: "search", lane: "follow", only: [down.cell.place], insist: true })
    await flushPromises()
    expect(signals[1]?.aborted).toBe(true)
    expect(pendingOf(tab.state.value).map((cell) => cell.planned.key)).toEqual([down.key])
    expect(tab.state.value.cells.find((cell) => cell.planned.key === late.key)?.outcome?.status).toBe("late")
    scope.stop()
  })

  it("says what was still being asked was stopped when the person stops it", async () => {
    const ask: Ask = (_, signal) =>
      (async function* () {
        yield PLAN
        await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve()))
      })()
    const scope = effectScope()
    const tab = scope.run(() => useTabAnswer(ask))!
    void tab.search({ words: "orders", mode: "search", lane: "tab" })
    await flushPromises()
    expect(pendingOf(tab.state.value)).toHaveLength(1)
    tab.stop()
    await flushPromises()
    expect(pendingOf(tab.state.value)).toEqual([])
    expect(tab.state.value.cells[0]?.outcome?.message).toBe(STOPPED_BEFORE_ANSWER)
    expect(tab.searching.value).toBe(false)
    scope.stop()
  })

  it("does not leave a place searching when the answer ends without it", async () => {
    const { ask } = scripted([PLAN, { type: "end", nothing_found: false, asked: 1, superseded: true }])
    const scope = effectScope()
    const tab = scope.run(() => useTabAnswer(ask))!
    await tab.search({ words: "orders", mode: "search", lane: "tab" })
    expect(pendingOf(tab.state.value)).toEqual([])
    scope.stop()
  })

  it("is told how an answer ended, follow-ups included", async () => {
    const ended = vi.fn()
    const { ask } = scripted([PLAN, { type: "end", nothing_found: false, asked: 1, superseded: false }])
    const scope = effectScope()
    const tab = scope.run(() => useTabAnswer(ask, ended))!
    await tab.search({ words: "orders", mode: "search", lane: "tab" })
    expect(ended).toHaveBeenCalledWith(expect.objectContaining({ mode: "typing" }), "orders")
    scope.stop()
  })
})
