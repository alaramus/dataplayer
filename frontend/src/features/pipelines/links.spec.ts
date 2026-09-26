import { describe, expect, it } from "vitest"

import type { Card, Link, LinkRun, PasteOffer } from "@/client"

import {
  endOf,
  hintEdges,
  hintOf,
  joinProblem,
  keptLinks,
  linkBetween,
  linkEdge,
  linkFromOffer,
  listed,
  missingChoice,
  nodeIdOf,
  refusal,
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

  it("asks for columns before a table is made or filled", () => {
    const create = offer("rows_new_relation", "Create a table", { workflow: "new-relation" })
    const into = offer("rows_into_relation", "Add rows to a table", { workflow: "into-relation" })
    const bare: Link = { ...saving, kind: "rows_new_relation", title: "Create a table" }
    expect(missingChoice(bare, create)).toBe("Choose the new table's name and columns first")
    expect(missingChoice({ ...bare, name: "t", columns: [{ source: "a", target: "a", type_code: "text" }] }, create)).toBeNull()
    expect(missingChoice(bare, into)).toBe("Pair the columns first")
    expect(missingChoice(saving, csv)).toBeNull()
  })

  it("goes with the rows it joins when they are unticked", () => {
    const fromSchema: Link = { ...saving, id: "l2", source: { card_id: "sales", node_id: "public" } }
    expect(keptLinks([saving, fromSchema], "sales", [sales.rows[0]!])).toEqual([saving])
    expect(keptLinks([saving, fromSchema], "files", files.rows)).toEqual([saving, fromSchema])
    expect(keptLinks([saving], "files", [files.rows[0]!])).toEqual([])
  })

  it("is said in words, and so is its last run", () => {
    const name = (end: Link["source"]) => `${end.card_id} · ${end.node_id ?? "top"}`
    expect(sentence(saving, name)).toBe("Save as CSV: sales · public.orders → files · reports")
    expect(listed([saving, saving], name)).toBe("sales · public.orders → files · reports; sales · public.orders → files · reports")

    const now = Date.parse("2026-09-26T12:10:00Z")
    const done: LinkRun = {
      link_id: "l1", outcome: "done", message: "orders.csv saved in reports",
      started_at: "2026-09-26T12:06:00Z", finished_at: "2026-09-26T12:07:00Z",
    }
    expect(runWords(done, now)).toBe("Done 3m ago: orders.csv saved in reports")
    expect(runWords({ ...done, outcome: "running", message: null, finished_at: null }, now)).toBe("Running")
    expect(runWords(undefined, now)).toBe("Not run yet")
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
