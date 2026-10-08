import { describe, expect, it } from "vitest"

import type { Card, Link, LinkRun, PasteOffer, PipelineRunPublic } from "@/client"

import {
  chainOf,
  dependents,
  endOf,
  hintEdges,
  hintOf,
  joinProblem,
  keptLinks,
  linkBetween,
  linkEdge,
  linkFromOffer,
  listed,
  madeRows,
  needsDialog,
  nodeIdOf,
  refusal,
  runProblem,
  runWords,
  sentence,
  usable,
  withOffer,
} from "./links"

const sales: Card = {
  id: "sales", connector_id: "db", connector_name: "Sales", x: 0, y: 0,
  rows: [
    { node_id: "public.orders", label: "orders", kind: "table", trail: ["public"] },
    { node_id: "public", label: "public", kind: "schema", trail: [] },
  ],
}
const files: Card = {
  id: "files", connector_id: "storage", connector_name: "Files", x: 400, y: 0,
  rows: [
    { node_id: null, label: "Files", kind: null, trail: [] },
    { node_id: "reports", label: "reports", kind: "directory", trail: [] },
  ],
}
const sameSales: Card = { ...sales, id: "sales-2" }

function offer(kind: PasteOffer["kind"], title: string, more: Partial<PasteOffer> = {}): PasteOffer {
  return { kind, title, available: true, ...more }
}

const csv = offer("relation_csv", "Save as CSV", { workflow: "file-name", suggested_name: "orders.csv" })
const saving = linkFromOffer("l1", { card_id: "sales", node_id: "public.orders" }, { card_id: "files", node_id: "reports" }, csv)

describe("a link between two rows", () => {
  it("names its ends by the rows of the canvas, the top of a connection by none", () => {
    expect(endOf({ nodeId: "files", portId: "top" })).toEqual({ card_id: "files", node_id: null })
    expect(endOf({ nodeId: "sales", portId: "node:public.orders" })).toEqual({ card_id: "sales", node_id: "public.orders" })
    expect(nodeIdOf("node:node:x")).toBe("node:x")
  })

  it("is drawn from row to row, labelled by what it does", () => {
    expect(linkEdge(saving)).toEqual({
      id: "l1",
      source: { nodeId: "sales", portIds: ["node:public.orders"] },
      target: { nodeId: "files", portIds: ["node:reports"] },
      label: "Save as CSV",
      directed: true,
    })
    expect(saving).toMatchObject({ kind: "relation_csv", conflict: "refuse", name: null, columns: null })
  })

  it("is refused before asking when it starts at a top or stays in one connection", () => {
    const cards = [sales, files, sameSales]
    expect(joinProblem(cards, { card_id: "files", node_id: null }, { card_id: "sales", node_id: "public" })).toMatch(/top of a connection/)
    expect(joinProblem(cards, { card_id: "sales", node_id: "public.orders" }, { card_id: "sales-2", node_id: "public" })).toMatch(/one connection/)
    expect(joinProblem(cards, saving.source, saving.target)).toBeNull()
    expect(joinProblem(cards, saving.source, { card_id: "gone", node_id: null })).toMatch(/no longer on the canvas/)
  })

  it("is drawn only for an offer it can run, and says why when there is none", () => {
    const refused = offer("rows_new_relation", "Create a table", { available: false, reason: "This cannot be read as rows" })
    const taken = offer("relation_csv", "Save as CSV", { available: false, name_conflict: true, reason: "orders.csv is already there" })
    expect(usable([refused, taken])).toEqual([taken])
    expect(refusal([refused])).toBe("This cannot be read as rows")
    expect(refusal([])).toBe("Nothing can go from that row into this one")
  })

  it("is found again between the same two rows, one way round only", () => {
    expect(linkBetween([saving], saving.source, saving.target)).toBe(saving)
    expect(linkBetween([saving], saving.target, saving.source)).toBeNull()
  })

  it("forgets its choices when it is made to do something else", () => {
    const chosen: Link = { ...saving, name: "all.csv", conflict: "replace" }
    expect(withOffer(chosen, csv)).toBe(chosen)
    expect(withOffer(chosen, offer("rows_new_relation", "Create a table"))).toMatchObject({
      kind: "rows_new_relation", title: "Create a table", name: null, conflict: "refuse", columns: null,
    })
  })

  it("is numbered by its place in a run and coloured by what it did in the last", () => {
    const place = { link_id: "l1", number: 2, circle: null }
    const drawn = linkEdge(saving, place, { link_id: "l1", outcome: "done" })
    expect(drawn).toMatchObject({ badge: "2", label: "Save as CSV", tone: "success" })
    expect(drawn.caution).toBeUndefined()
    expect(linkEdge(saving, place, { link_id: "l1", outcome: "running" }).tone).toBe("info")
    expect(linkEdge(saving, place, { link_id: "l1", outcome: "failed" }).tone).toBe("error")
    expect(linkEdge(saving, place, { link_id: "l1", outcome: "not_run" }).tone).toBe("muted")
    // Still to come in a run going on: the plain line.
    expect(linkEdge(saving, place, { link_id: "l1", outcome: "waiting" }).tone).toBeUndefined()
    // Where the arrows gave no first link, the number says why.
    const broken = linkEdge(saving, { ...place, circle: "Sales and Files write into each other" })
    expect(broken).toMatchObject({ badge: "2", caution: "Sales and Files write into each other" })
  })

  it("goes with the rows it joins when they are unticked", () => {
    const fromSchema: Link = { ...saving, id: "l2", source: { card_id: "sales", node_id: "public" } }
    expect(keptLinks([saving, fromSchema], "sales", [sales.rows[0]!])).toEqual([saving])
    expect(keptLinks([saving, fromSchema], "files", files.rows)).toEqual([saving, fromSchema])
    expect(keptLinks([saving], "files", [files.rows[0]!])).toEqual([])
  })

  it("is said in words, and so is its part in a run", () => {
    const name = (end: Link["source"]) => `${end.card_id} · ${end.node_id ?? "top"}`
    expect(sentence(saving, name)).toBe("Save as CSV: sales · public.orders → files · reports")
    expect(listed([saving, saving], name)).toBe("sales · public.orders → files · reports; sales · public.orders → files · reports")

    const now = Date.parse("2026-09-26T12:10:00Z")
    const done: LinkRun = {
      link_id: "l1", outcome: "done", message: "orders.csv saved in reports", finished_at: "2026-09-26T12:07:00Z",
    }
    const run: PipelineRunPublic = {
      job_id: "j1", state: "failed", message: "Stopped at 2 of 3, Save as CSV: taken; 1 not run",
      started_at: "2026-09-26T12:06:00Z", finished_at: "2026-09-26T12:08:00Z",
      links: [done, { link_id: "l2", outcome: "failed", message: "taken" }, { link_id: "l3", outcome: "not_run" }],
    }
    expect(runWords(done, run, now)).toBe("Done 3m ago: orders.csv saved in reports")
    expect(runWords(run.links[2], run, now)).toBe("Not run: the run stopped before it")
    expect(runWords(undefined, run, now)).toBe("Drawn since the last run")
    expect(runWords(undefined, run, now, true)).toBe("Drawn since this run")
    expect(runWords(undefined, null, now)).toBe("Not run yet")
    const going: PipelineRunPublic = {
      ...run, state: "running", message: null, finished_at: null,
      links: [done, { link_id: "l2", outcome: "running" }, { link_id: "l3", outcome: "waiting" }],
    }
    expect(runWords(going.links[1], going, now)).toBe("Running")
    expect(runWords(going.links[2], going, now)).toBe("Waiting for the links before it")
  })

  it("is run whole, once there is a link and while no run is going", () => {
    const run: PipelineRunPublic = {
      job_id: "j1", state: "running", message: null, started_at: "2026-09-26T12:06:00Z", finished_at: null, links: [],
    }
    expect(runProblem([], null)).toBe("Draw a link first")
    expect(runProblem([saving], run)).toBe("This pipeline is running; Stop is in the activity below")
    expect(runProblem([saving], { ...run, state: "succeeded" })).toBeNull()
  })

  it("opens its window at once while its table or columns are still missing", () => {
    expect(needsDialog(saving, "file-name")).toBe(false)
    expect(needsDialog({ ...saving, kind: "rows_new_relation" }, "new-relation")).toBe(true)
    expect(needsDialog({ ...saving, kind: "rows_new_relation", name: "orders", columns: [] }, "new-relation")).toBe(true)
    expect(
      needsDialog({ ...saving, kind: "rows_new_relation", name: "orders", columns: [{ source: "id", target: "id" }] }, "new-relation")
    ).toBe(false)
    expect(needsDialog({ ...saving, kind: "rows_into_relation" }, "into-relation")).toBe(true)
    expect(
      needsDialog({ ...saving, kind: "rows_into_relation", columns: [{ source: "id", target: "id" }] }, "into-relation")
    ).toBe(false)
  })
})

describe("the hint", () => {
  it("draws what could be made dashed, and turns a pressed one back into its ends", () => {
    const hints = [
      { source: saving.source, target: saving.target, titles: ["Save as CSV"] },
      { source: { card_id: "files", node_id: "reports" }, target: { card_id: "sales", node_id: "public" }, titles: ["Create a table", "Add rows"] },
    ]
    const [first, second] = hintEdges(hints)
    expect(first).toMatchObject({ id: "hint:0", dashed: true, label: "Save as CSV" })
    expect(second?.label).toBe("Create a table · Add rows")
    expect(hintOf(hints, "hint:1")).toBe(hints[1])
    expect(hintOf(hints, "l1")).toBeNull()
    expect(hintOf(hints, "hint:9")).toBeNull()
  })
})

describe("a chain: what a link makes, read by the next (D178)", () => {
  const save: Link = { ...saving, id: "save" }
  const copy: Link = {
    ...saving, id: "copy", kind: "file_copy", title: "Copy files",
    source: { card_id: "files", node_id: null, made_by: "save" },
    target: { card_id: "sales", node_id: "public" },
  }
  const load: Link = {
    ...saving, id: "load", kind: "rows_new_relation", title: "Create a table",
    source: { card_id: "sales", node_id: null, made_by: "copy" },
    target: { card_id: "files", node_id: "reports" },
  }

  it("names a result by the link that makes it, as a row of the card it goes into", () => {
    expect(endOf({ nodeId: "files", portId: "made:save" })).toEqual({ card_id: "files", node_id: null, made_by: "save" })
    expect(linkEdge(copy).source).toEqual({ nodeId: "files", portIds: ["made:save"] })
    // A result is something to take, where the top of a connection is not.
    expect(joinProblem([sales, files], copy.source, copy.target)).toBeNull()
    expect(linkBetween([copy], { card_id: "files", node_id: null }, copy.target)).toBeNull()
  })

  it("draws each result below the row its link writes into, numbered by its maker", () => {
    const made = madeRows(
      [{ link_id: "save", card_id: "files", name: "orders.csv", kind: "file" }],
      [save],
      new Map([["save", { link_id: "save", number: 1 }]])
    )
    expect(made).toEqual([{
      cardId: "files",
      after: "node:reports",
      row: { id: "made:save", label: "orders.csv", detail: "← 1", icon: expect.any(String) as string, made: true },
    }])
    // A link the draft no longer holds draws nothing.
    expect(madeRows([{ link_id: "gone", card_id: "files", name: "x", kind: "file" }], [save], new Map())).toEqual([])
  })

  it("takes along every link reading what goes, however far along", () => {
    expect(dependents([save, copy, load], new Set(["save"])).map((link) => link.id)).toEqual(["copy", "load"])
    expect(dependents([save, copy, load], new Set(["load"]))).toEqual([])
    // Unticking the folder the file is saved into takes the whole chain.
    expect(keptLinks([save, copy, load], "files", [files.rows[0]!]).map((link) => link.id)).toEqual([])
    expect(chainOf([save, copy, load], load.source).map((link) => link.id)).toEqual(["copy", "save"])
    expect(chainOf([save], { card_id: "files", node_id: "reports" })).toEqual([])
  })
})
