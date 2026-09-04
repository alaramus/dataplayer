import { describe, expect, it, vi } from "vitest"

import type { RelationModel } from "@/client"
import { GRAPH_LIMITS } from "@/shared/graph/model"
import { GraphLoadError, loadRelations } from "./load"

const scope = (size: number) => Array.from({ length: size }, (_, id) => ({ id: String(id), label: `Table ${id}` }))
const model = (id: string): RelationModel => ({ node_id: id, name: `Table ${id}`, kind: "table", columns: [] })

describe("bounded relationship loading", () => {
  it("keeps at most four reads in flight and reports partial failures without leaking exceptions", async () => {
    const pending: Array<() => void> = []
    let active = 0
    let peak = 0
    const read = vi.fn((id: string) => new Promise<RelationModel>((resolve, reject) => {
      active++; peak = Math.max(peak, active)
      pending.push(() => { active--; if (id === "2") reject(new Error("password=secret")); else resolve(model(id)) })
    }))
    const progress = vi.fn()
    const result = loadRelations(scope(6), read, new AbortController().signal, progress)
    expect(read).toHaveBeenCalledTimes(4)
    for (let done = 0; done < 6; done++) {
      pending.shift()!()
      await Promise.resolve()
    }
    const loaded = await result
    expect(peak).toBe(4)
    expect(loaded.models).toHaveLength(5)
    expect(loaded.failures).toEqual([{ id: "2", label: "Table 2", message: "Could not read this structure" }])
    expect(progress.mock.calls.map(([count]) => count)).toEqual([1, 2, 3, 4, 5, 6])
  })

  it("aborts in-flight reads and never starts queued reads after cancellation", async () => {
    const stop = new AbortController()
    const signals: AbortSignal[] = []
    const read = vi.fn((_id: string, signal: AbortSignal) => new Promise<RelationModel>((_resolve, reject) => {
      signals.push(signal)
      signal.addEventListener("abort", () => reject(signal.reason), { once: true })
    }))
    const progress = vi.fn()
    const loaded = loadRelations(scope(8), read, stop.signal, progress)
    const rejected = expect(loaded).rejects.toMatchObject({ name: "AbortError" })
    stop.abort()
    await rejected
    expect(read).toHaveBeenCalledTimes(4)
    expect(signals.every((signal) => signal.aborted)).toBe(true)
    expect(progress).not.toHaveBeenCalled()
  })

  it("refuses large scopes before reading and stops once structures exceed the graph budget", async () => {
    const read = vi.fn(async (id: string) => model(id))
    await expect(loadRelations(scope(101), read, new AbortController().signal, vi.fn())).rejects.toBeInstanceOf(GraphLoadError)
    expect(read).not.toHaveBeenCalled()
    const oversized = vi.fn(async (id: string, signal: AbortSignal): Promise<RelationModel> => {
      signal.throwIfAborted()
      return { ...model(id), columns: Array.from({ length: GRAPH_LIMITS.rows + 1 }, (_, position) => ({ position, name: String(position), type: { sql: "text", category: "string" }, nullable: true })) }
    })
    await expect(loadRelations(scope(12), oversized, new AbortController().signal, vi.fn())).rejects.toThrow("Select fewer tables")
    expect(oversized).toHaveBeenCalledTimes(4)
  })
})
