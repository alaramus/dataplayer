import { describe, expect, it } from "vitest"

import { createOperations, isActive } from "./operations"

describe("local operation checkpoints", () => {
  it("pauses after the sent request, resumes once and stops before the next request", async () => {
    const registry = createOperations()
    const task = registry.start("Upload", 3)
    expect(await task.next("first.csv")).toBe(true)
    registry.pause(task.id)
    expect(registry.items.value[0]?.state).toBe("pausing")
    task.complete()
    let dispatched = false
    const next = task.next("second.csv").then((answer) => { dispatched = answer; return answer })
    await Promise.resolve()
    expect(dispatched).toBe(false)
    expect(registry.items.value[0]?.state).toBe("paused")
    registry.resume(task.id)
    expect(await next).toBe(true)
    registry.stop(task.id)
    task.complete()
    expect(await task.next("third.csv")).toBe(false)
    task.finish("Stopped with one request left")
    expect(registry.items.value[0]).toMatchObject({ state: "cancelled", completed: 2, total: 3 })
  })

  it("stopping a paused queue releases the waiter without sending another request", async () => {
    const registry = createOperations()
    const task = registry.start("Delete", 2)
    await task.next("first")
    registry.pause(task.id)
    task.complete()
    const next = task.next("second")
    registry.stop(task.id)
    expect(await next).toBe(false)
    task.finish("Stopped")
    expect(isActive(registry.items.value[0]!)).toBe(false)
  })

  it("finishing upload transport does not finish the request", async () => {
    const registry = createOperations()
    const task = registry.start("Upload", 1)
    await task.next("data.csv")
    task.transfer(80, 100)
    expect(registry.items.value[0]?.transfer).toEqual({ loaded: 80, total: 100 })
    task.transfer(100, 100)
    expect(registry.items.value[0]).toMatchObject({
      state: "running", completed: 0, canPause: false, canStop: false,
      detail: "Upload sent; waiting for the server",
    })
    task.fail("The server refused the file")
    expect(registry.items.value[0]?.state).toBe("failed")
  })

  it("clears session history and releases paused queues without resurrecting them", async () => {
    const registry = createOperations()
    const task = registry.start("Copy", 2)
    await task.next("first")
    registry.pause(task.id)
    task.complete()
    const waiting = task.next("second")
    registry.clear()
    expect(await waiting).toBe(false)
    task.finish("Stopped")
    expect(registry.items.value).toEqual([])
  })

  it("retains active work while bounding and clearing finished history", async () => {
    const registry = createOperations()
    const active = registry.start("Archive", 1)
    for (let index = 0; index < 60; index++) {
      const task = registry.start("Delete", 1)
      await task.next("file")
      task.complete()
      task.finish("Deleted")
    }
    expect(registry.items.value).toHaveLength(51)
    const secondActive = registry.start("Extract", 1)
    await active.next("files")
    active.complete()
    active.finish("Archived")
    expect(registry.items.value).toHaveLength(51)
    expect(registry.items.value.some((item) => item.id === active.id)).toBe(true)
    registry.clearFinished()
    expect(registry.items.value.map((item) => item.id)).toEqual([secondActive.id])
  })
})
