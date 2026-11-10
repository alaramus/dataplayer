import { beforeEach, describe, expect, it, vi } from "vitest"

import { createPipelineKey } from "@/features/pipelines/api"

import { currentChapter, endTour, nextChapter, offerMutation, prepared, startTour, tourState } from "./runner"
import { AGENT_TOUR, DASHBOARDS_TOUR, PIPELINE_TOUR, SHORT_TOURS, VIEWS_TOUR } from "./shortTours"
import type { TourKit } from "./tour"

function kit(): TourKit & { calls: string[] } {
  const calls: string[] = []
  return {
    calls,
    makePractice: vi.fn(async () => {
      calls.push("make")
      return { id: "p1", name: "practice", path: "databases/practice.db" }
    }),
    ensureFolder: vi.fn(async () => {
      calls.push("folder")
      return { id: "f1", name: "My files" }
    }),
    removeWithFile: vi.fn(async (id: string) => {
      calls.push(`remove ${id}`)
    }),
    removePipeline: vi.fn(async (id: string) => {
      calls.push(`pipeline ${id}`)
    }),
  }
}

describe("the short tours", () => {
  beforeEach(() => endTour())

  it("are four, each named, summed up and with a hint for every target", () => {
    expect(SHORT_TOURS.map((tour) => tour.id)).toEqual(["views", "pipeline", "dashboards", "agent"])
    for (const tour of SHORT_TOURS) {
      expect(tour.title()).not.toBe("")
      expect(tour.summary()).not.toBe("")
      for (const chapter of tour.chapters) {
        expect(chapter.title()).not.toBe("")
        for (const target of chapter.targets) expect(target.hint({})).not.toBe("")
      }
    }
  })

  it("only show where dashboards and the agent are: every chapter is closed by Next or by a screen opening", () => {
    for (const tour of [DASHBOARDS_TOUR, AGENT_TOUR]) {
      expect(tour.setup).toBeUndefined()
      expect(tour.chapters.every((chapter) => chapter.done.kind !== "mutation")).toBe(true)
    }
  })

  it("make a practice database first and take it away with its file after", async () => {
    const tools = kit()
    startTour(VIEWS_TOUR)
    expect(tourState.preparing).toBe(true)
    expect(currentChapter.value).toBeNull()
    prepared(await (VIEWS_TOUR.setup?.(tools) ?? Promise.resolve({})))
    expect(tourState.memory.database).toEqual({ id: "p1", name: "practice", folder: "databases", file: "practice.db" })
    expect(currentChapter.value?.id).toBe("views-open")
    await VIEWS_TOUR.cleanup?.(tools, tourState.memory)
    expect(tools.calls).toEqual(["make", "remove p1"])
  })

  it("make the pipeline's folder too, and take the pipeline with the database", async () => {
    const tools = kit()
    startTour(PIPELINE_TOUR)
    prepared(await (PIPELINE_TOUR.setup?.(tools) ?? Promise.resolve({})))
    expect(tourState.memory.folder).toEqual({ id: "f1", name: "My files" })
    offerMutation({ key: createPipelineKey, variables: "Pipeline", data: { id: "pl1" } })
    expect(currentChapter.value?.id).toBe("pipeline-source")
    await PIPELINE_TOUR.cleanup?.(tools, tourState.memory)
    expect(tools.calls).toEqual(["make", "folder", "pipeline pl1", "remove p1"])
  })

  it("go on from a shown chapter by Next, and only from one", () => {
    startTour(AGENT_TOUR)
    expect(currentChapter.value?.id).toBe("agent-space")
    nextChapter()
    expect(currentChapter.value?.id).toBe("agent-space")
    // A chapter only shown goes on by its button.
    startTour({ ...AGENT_TOUR, chapters: AGENT_TOUR.chapters.slice(3) })
    nextChapter()
    expect(currentChapter.value?.id).toBe("agent-attach")
  })
})
