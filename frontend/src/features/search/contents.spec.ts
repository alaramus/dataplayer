import { describe, expect, it } from "vitest"

import type { ContentsPlace, JobPublic } from "@/client"
import { forgetContentsWords } from "@/shared/search/contentsWords"

import { EMPTY_ANSWER, reduceAnswer } from "./answer"
import {
  contentsChoices, contentsCounts, contentsExpired, contentsMeasure, contentsWordsOf,
  heldUntil, placeSentence, rememberContentsWords,
} from "./contents"
import { hitOption } from "./rows"
import { CONNECTIONS, hit, IN_PG, plannedCell } from "./testing"

const FILES = { key: "connection:f1", title: "my files", rank: 1001 }

function job(over: Partial<JobPublic> = {}): JobPublic {
  return {
    id: "job-1",
    kind: "search.contents",
    subject_id: null,
    parameters: { connections: 2, searched: 1, found: 3, held_seconds: 1800 },
    state: "succeeded",
    step: null,
    step_index: 1,
    step_count: 1,
    message: "3 matches found in 2 connections",
    created_at: "2026-10-03T12:00:00Z",
    started_at: "2026-10-03T12:00:00Z",
    finished_at: "2026-10-03T12:00:10Z",
    ...over,
  }
}

function place(over: Partial<ContentsPlace>): ContentsPlace {
  return {
    connector_id: "f1", name: "my files", status: "complete", reason: null,
    notice: null, error_kind: null, message: null, found: 0, ...over,
  }
}

describe("a search inside files", () => {
  it("offers the connections of the answer that can be searched inside, once each", () => {
    const state = reduceAnswer(EMPTY_ANSWER, {
      type: "plan",
      mode: "search",
      cells: [
        plannedCell("connections/names", CONNECTIONS),
        plannedCell("connection:c1/names", IN_PG),
        plannedCell("connection:f1/names", FILES, { contents: true }),
        plannedCell("connection:f1/columns", FILES, { contents: true }),
      ],
    })

    expect(contentsChoices(state)).toEqual([{ connectorId: "f1", name: "my files" }])
  })

  it("is measured by its row's counts and never by its words", () => {
    const counts = contentsCounts(job())

    expect(counts).not.toBeNull()
    expect(contentsMeasure(counts ?? { connections: 0, searched: 0, found: 0, heldSeconds: 0 }))
      .toBe("1 of 2 connections · 3 found")
    expect(contentsCounts(job({ kind: "paste.transfer" }))).toBeNull()
  })

  it("knows when the server lets its matches go", () => {
    const ended = Date.parse("2026-10-03T12:00:10Z")

    expect(heldUntil(job())).toBe(ended + 1800 * 1000)
    expect(heldUntil(job({ finished_at: null, state: "running" }))).toBeNull()
    expect(contentsExpired(job(), ended + 1799 * 1000)).toBe(false)
    expect(contentsExpired(job(), ended + 1800 * 1000)).toBe(true)
  })

  it("says what became of each place it was asked", () => {
    expect(placeSentence(place({}))).toBeNull()
    expect(placeSentence(place({ status: "stopped", notice: "Stopped on request" }))).toBe("Stopped on request")
    expect(placeSentence(place({ status: "failed", message: "Locked by its owner" }))).toBe("Locked by its owner")
    expect(placeSentence(place({ status: "skipped", reason: "switched_off" }))).toBe("Switched off")
    expect(placeSentence(place({ status: "waiting" }))).toBe("Waiting")
  })

  it("keeps the words of a search started here in memory until sign-out", () => {
    rememberContentsWords("job-1", "needle")

    expect(contentsWordsOf("job-1")).toBe("needle")
    forgetContentsWords()
    expect(contentsWordsOf("job-1")).toBeNull()
  })

  it("draws a found line with its number before the marked words", () => {
    const found = hit("node:f1:notes/a.txt:", {
      title: "a.txt",
      match: {
        field: "contents", match_class: "text", line: 3,
        excerpt: [{ text: "alpha ", hit: false }, { text: "needle", hit: true }],
      },
    })

    expect(hitOption(found).descriptionRuns).toEqual([
      { text: "Line 3: ", hit: false },
      { text: "alpha ", hit: false },
      { text: "needle", hit: true },
    ])
  })
})
