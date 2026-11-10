import { beforeEach, describe, expect, it } from "vitest"

import { createConnectorKey, deleteConnectorKey, makeConnectorHereKey } from "@/features/connectors/api"
import { runActionKey } from "@/features/catalog/api"
import { updateCellKey } from "@/features/grid/api"
import { startRunKey } from "@/features/queries/runs"

import { BASICS } from "./basics"
import { checkShown, currentChapter, endTour, offerMutation, startTour, tourFinished, tourState } from "./runner"

const made = {
  key: makeConnectorHereKey,
  variables: { adapter_type: "sqlite", choice: {} },
  data: { id: "c1", name: "dataplayer", config: { path: "/databases/dataplayer (1).db" } },
}

function chapterId() {
  return currentChapter.value?.id
}

describe("the first tour", () => {
  beforeEach(() => {
    endTour()
    startTour()
  })

  it("is nine chapters, each with a hint for every target", () => {
    expect(BASICS.map((chapter) => chapter.id)).toEqual([
      "make", "open", "filter", "edit", "query", "disconnect", "folder", "find", "remove",
    ])
    for (const chapter of BASICS) {
      expect(chapter.targets.length).toBeGreaterThan(0)
      expect(chapter.title()).not.toBe("")
      for (const target of chapter.targets) expect(target.hint({})).not.toBe("")
    }
  })

  it("remembers the database it made, under the name the server gave", () => {
    offerMutation(made)
    expect(chapterId()).toBe("open")
    expect(tourState.memory.database).toEqual({
      id: "c1",
      name: "dataplayer",
      folder: "databases",
      file: "dataplayer (1).db",
    })
  })

  it("waits for the mutation its chapter is about, not for any", () => {
    offerMutation({ ...made, key: createConnectorKey })
    expect(chapterId()).toBe("make")
    offerMutation({ ...made, data: null })
    expect(chapterId()).toBe("make")
  })

  it("is walked to the end by the operations of each chapter", () => {
    offerMutation(made)
    // "open" and "filter" end when a control appears; the host reads the page.
    const shown = () => ({}) as Element
    checkShown(shown)
    checkShown(shown)
    expect(chapterId()).toBe("edit")
    offerMutation({ key: updateCellKey, variables: {}, data: {} })
    // A query on another connection is not the one asked for.
    offerMutation({ key: startRunKey, variables: { connector_id: "other" }, data: {} })
    expect(chapterId()).toBe("query")
    offerMutation({ key: startRunKey, variables: { connector_id: "c1" }, data: {} })
    offerMutation({ key: deleteConnectorKey, variables: "other", data: null })
    expect(chapterId()).toBe("disconnect")
    offerMutation({ key: deleteConnectorKey, variables: "c1", data: null })
    offerMutation({ key: createConnectorKey, variables: { adapter_type: "postgres" }, data: { id: "p", name: "p" } })
    expect(chapterId()).toBe("folder")
    offerMutation({ key: createConnectorKey, variables: { adapter_type: "file" }, data: { id: "f1", name: "Files" } })
    expect(tourState.memory.folder).toEqual({ id: "f1", name: "Files" })
    checkShown(shown)
    expect(chapterId()).toBe("remove")
    // Another file deleted, or this one refused, does not end the tour.
    offerMutation({ key: runActionKey, variables: { name: "delete", nodeIds: ["databases/other.db"] }, data: { failures: [] } })
    offerMutation({
      key: runActionKey,
      variables: { name: "delete", nodeIds: ["databases/dataplayer (1).db"] },
      data: { failures: [{}] },
    })
    expect(tourFinished.value).toBe(false)
    offerMutation({
      key: runActionKey,
      variables: { name: "delete", nodeIds: ["databases/dataplayer (1).db"] },
      data: { failures: [] },
    })
    expect(tourFinished.value).toBe(true)
  })

  it("hears nothing once ended", () => {
    endTour()
    offerMutation(made)
    expect(tourState.chapter).toBe(0)
    expect(currentChapter.value).toBeNull()
  })
})
