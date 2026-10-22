import { describe, expect, it, vi } from "vitest"

import type { ReferenceEndPublic, RelationModel, RelationModelsResult } from "@/client"
import type { CatalogNode } from "@/features/catalog/nodes"
import { GRAPH_LIMITS } from "@/shared/graph/model"
import { expandHolders, GraphLoadError, loadRelations, withDeclared } from "./load"

const scope = (size: number) =>
  Array.from({ length: size }, (_, id) => ({ id: String(id), label: `Table ${id}` }))
const model = (id: string): RelationModel => ({
  node_id: id,
  name: `Table ${id}`,
  kind: "table",
  columns: [],
})
const batch = (
  models: RelationModel[],
  failures: RelationModelsResult["failures"] = [],
): RelationModelsResult => ({ models, failures })

describe("bounded relationship loading", () => {
  it("does not send an empty batch", async () => {
    const read = vi.fn(async (ids: string[]) => batch(ids.map(model)))

    const result = await loadRelations([], read, new AbortController().signal)

    expect(result.models).toEqual([])
    expect(read).not.toHaveBeenCalled()
  })

  it("reads a set once and keeps per-node failures in the graph", async () => {
    const read = vi.fn(async (nodeIds: string[]) =>
      batch(
        nodeIds.filter((id) => id !== "2").map(model),
        [{ node_id: "2", message: "Could not read Table 2" }],
      ))
    const result = loadRelations(scope(6), read, new AbortController().signal)
    expect(read).toHaveBeenCalledTimes(1)
    const loaded = await result
    expect(loaded.models).toHaveLength(5)
    expect(loaded.failures).toEqual([
      { id: "2", label: "Table 2", message: "Could not read Table 2" },
    ])
  })

  it("keeps unexpected batch errors behind the safe fallback", async () => {
    const read = vi.fn(async (_nodeIds: string[]) => {
      throw new Error("password=secret")
    })

    const result = await loadRelations(
      scope(2),
      read,
      new AbortController().signal,
    )

    expect(result.failures).toHaveLength(2)
    expect(
      result.failures.every((failure) => !failure.message.includes("secret")),
    ).toBe(true)
  })

  it("aborts an in-flight batch read", async () => {
    const stop = new AbortController()
    const read = vi.fn(
      (_ids: string[], signal: AbortSignal) =>
        new Promise<RelationModelsResult>((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(signal.reason), { once: true })
        }),
    )
    const loaded = loadRelations(scope(8), read, stop.signal)
    const rejected = expect(loaded).rejects.toMatchObject({ name: "AbortError" })
    stop.abort()
    await rejected
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("refuses large scopes before reading and rejects a batch over the graph budget", async () => {
    const read = vi.fn(async (ids: string[]) => batch(ids.map(model)))
    await expect(loadRelations(scope(101), read, new AbortController().signal))
      .rejects.toBeInstanceOf(GraphLoadError)
    expect(read).not.toHaveBeenCalled()
    const oversized = vi.fn(async (ids: string[]) =>
      batch(
        ids.map((id) => ({
          ...model(id),
          columns: Array.from(
            { length: GRAPH_LIMITS.rows + 1 },
            (_, position) => ({
              position,
              name: String(position),
              type: { sql: "text", category: "string" },
              nullable: true,
            }),
          ),
        })),
      ))
    await expect(loadRelations(scope(12), oversized, new AbortController().signal))
      .rejects.toThrow("Select fewer tables")
    expect(oversized).toHaveBeenCalledTimes(1)
  })
})

describe("what a diagram reads besides the selection", () => {
  it("draws a workbook as the relations directly inside it, and keeps one it cannot list", async () => {
    const sheet = (id: string, name: string): CatalogNode =>
      ({ kind: "dataset", id, name, has_children: false, representations: [], describable: true }) as CatalogNode
    const list = vi.fn(async (nodeId: string) => {
      if (nodeId === "broken.xlsx") throw new Error("unreadable")
      return [sheet("book.xlsx#0", "Sheet1"), sheet("book.xlsx#1", "Sheet2")]
    })
    const expanded = await expandHolders([
      { id: "a.csv", label: "a.csv" },
      { id: "book.xlsx", label: "book.xlsx", holdsNodes: true },
      { id: "broken.xlsx", label: "broken.xlsx", holdsNodes: true },
    ], list)
    expect(expanded).toEqual([
      { id: "a.csv", label: "a.csv" },
      { id: "book.xlsx#0", label: "Sheet1", group: "book.xlsx" },
      { id: "book.xlsx#1", label: "Sheet2", group: "book.xlsx" },
      { id: "broken.xlsx", label: "broken.xlsx" },
    ])
  })

  it("keeps the declared references that touch what was read, and reads each far end once from its own connection", async () => {
    const end = (connectorId: string, nodeId: string): ReferenceEndPublic => ({
      connector_id: connectorId, node_id: nodeId, column: "slug", connector_name: connectorId, adapter_type: "postgres", node_label: nodeId,
    })
    const references = [
      { id: "1", created_at: null, ends: [end("home", "0"), end("lab", "orgs")] as [ReferenceEndPublic, ReferenceEndPublic] },
      { id: "2", created_at: null, ends: [end("lab", "orgs"), end("home", "1")] as [ReferenceEndPublic, ReferenceEndPublic] },
      { id: "3", created_at: null, ends: [end("home", "9"), end("lab", "other")] as [ReferenceEndPublic, ReferenceEndPublic] },
    ]
    const read = vi.fn(async (far: ReferenceEndPublic) => model(far.node_id))
    const source = { requested: scope(2), models: [model("0"), model("1")], failures: [] }
    const result = await withDeclared(source, "home", references, read, new AbortController().signal)
    expect(result.declared!.map((reference) => reference.id)).toEqual(["1", "2"])
    expect(read).toHaveBeenCalledTimes(1)
    expect(read.mock.calls[0]![0]).toMatchObject({ connector_id: "lab", node_id: "orgs" })
    expect(result.far).toEqual([expect.objectContaining({ connectorId: "lab", nodeId: "orgs", model: model("orgs") })])
  })
})
