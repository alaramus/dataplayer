import { describe, expect, it } from "vitest"

import { chaptersToShow, furthestTarget, inCatalog, offersNext, sameKey, settleMutation, settledByShown, splitPath, testId } from "./tour"
import type { TourChapter, TourKit } from "./tour"
import { BASICS_TOUR } from "./basics"

const chapter: TourChapter = {
  id: "make",
  title: () => "Make",
  targets: [
    { locate: () => "#add", hint: () => "add" },
    { locate: () => "#pick", hint: () => "pick" },
    { locate: () => "#make", hint: () => "make", ready: (_, find) => find("#picked") !== null },
  ],
  done: { kind: "mutation", key: ["connectors", "make-here"], settle: (_, memory) => memory },
}

const finder = (shown: string[]) => (selector: string) =>
  shown.includes(selector) ? ({} as Element) : null

describe("furthestTarget", () => {
  it("rings the furthest control on screen", () => {
    expect(furthestTarget(chapter, {}, finder(["#add"]))).toBe(0)
    expect(furthestTarget(chapter, {}, finder(["#add", "#pick"]))).toBe(1)
  })

  it("passes over a control that is shown but not ready", () => {
    expect(furthestTarget(chapter, {}, finder(["#add", "#pick", "#make"]))).toBe(1)
    expect(furthestTarget(chapter, {}, finder(["#add", "#pick", "#make", "#picked"]))).toBe(2)
  })

  it("moves back when a window closes halfway", () => {
    expect(furthestTarget(chapter, {}, finder(["#add", "#pick"]))).toBe(1)
    expect(furthestTarget(chapter, {}, finder(["#add"]))).toBe(0)
  })

  it("says so when nothing of the chapter is on screen", () => {
    expect(furthestTarget(chapter, {}, finder([]))).toBe(-1)
  })

  it("skips a target that cannot be named yet", () => {
    const waiting: TourChapter = {
      ...chapter,
      targets: [{ locate: (memory) => (memory.folder ? "#folder" : null), hint: () => "" }],
    }
    expect(furthestTarget(waiting, {}, finder(["#folder"]))).toBe(-1)
    expect(furthestTarget(waiting, { folder: { id: "1", name: "f" } }, finder(["#folder"]))).toBe(0)
  })
})

describe("completion", () => {
  it("is settled by a mutation of the same key only", () => {
    const success = { key: ["connectors", "make-here"], variables: {}, data: {} }
    expect(settleMutation(chapter, success, {})).toEqual({})
    expect(settleMutation(chapter, { ...success, key: ["connectors", "create"] }, {})).toBeNull()
    expect(settleMutation(chapter, { ...success, key: undefined }, {})).toBeNull()
  })

  it("is settled by a control appearing", () => {
    const shown: TourChapter = { ...chapter, done: { kind: "shown", locate: () => "#count" } }
    expect(settledByShown(shown, {}, finder([]))).toBe(false)
    expect(settledByShown(shown, {}, finder(["#count"]))).toBe(true)
    expect(settledByShown(chapter, {}, finder(["#count"]))).toBe(false)
  })
})

describe("a chapter only shown", () => {
  const shown: TourChapter = { ...chapter, done: { kind: "next" } }

  it("offers Next on its last target, or when nothing of it is on screen", () => {
    expect(offersNext(shown, 2)).toBe(true)
    expect(offersNext(shown, -1)).toBe(true)
    expect(offersNext(shown, 1)).toBe(false)
    expect(offersNext(chapter, 2)).toBe(false)
  })

  it("can wait for several controls", () => {
    const two: TourChapter = { ...chapter, done: { kind: "shown", locate: () => "#card", atLeast: 2 } }
    const finder1 = finder(["#card"])
    expect(settledByShown(two, {}, finder1, () => 1)).toBe(false)
    expect(settledByShown(two, {}, finder1, () => 2)).toBe(true)
  })
})

describe("helpers", () => {
  it("escapes a name that came from the server", () => {
    expect(testId('connector-a"b')).toBe('[data-testid="connector-a\\"b"]')
  })

  it("finds a control inside one connection's catalog only", () => {
    expect(inCatalog("c1", "catalog-node-tasks")).toBe(
      '[data-testid="catalog-panel"][data-connector-id="c1"] [data-testid="catalog-node-tasks"]'
    )
  })

  it("compares keys part by part", () => {
    expect(sameKey(["a", "b"], ["a", "b"])).toBe(true)
    expect(sameKey(["a"], ["a", "b"])).toBe(false)
  })

  it("splits a stored path into a folder and a file", () => {
    expect(splitPath("/databases/dataplayer.db")).toEqual({ folder: "databases", file: "dataplayer.db" })
    expect(splitPath("a/b/c.db")).toEqual({ folder: "a/b", file: "c.db" })
    expect(splitPath("c.db")).toEqual({ folder: "", file: "c.db" })
  })
})

describe("chaptersToShow", () => {
  const kit = {} as TourKit
  const when = (answer: () => Promise<boolean>): TourChapter => ({ ...chapter, id: "later", when: answer })

  it("keeps a chapter without a condition and one whose condition holds", async () => {
    const shown = await chaptersToShow([chapter, when(async () => true)], kit)
    expect(shown.map((c) => c.id)).toEqual(["make", "later"])
  })

  it("leaves out a chapter whose condition fails or cannot be answered", async () => {
    expect(await chaptersToShow([chapter, when(async () => false)], kit)).toEqual([chapter])
    const broken = when(async () => {
      throw new Error("daemon")
    })
    expect(await chaptersToShow([chapter, broken], kit)).toEqual([chapter])
  })

  it("asks the first tour about its services chapter only", async () => {
    const asked: string[] = []
    const off = { canStartService: async (key: string) => (asked.push(key), false) } as unknown as TourKit
    const shown = await chaptersToShow(BASICS_TOUR.chapters, off)
    expect(shown.map((c) => c.id)).not.toContain("service")
    expect(shown).toHaveLength(BASICS_TOUR.chapters.length - 1)
    expect(asked).toEqual(["redis"])
  })
})
