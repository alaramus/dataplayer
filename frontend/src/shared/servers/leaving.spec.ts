import { describe, expect, it, vi } from "vitest"
import { createLeaveGuards } from "./leaving"

describe("server leave guards", () => {
  it("waits for a decision and stops switching when an editor refuses", async () => {
    const guards = createLeaveGuards()
    let decide: (value: boolean) => void = () => undefined
    guards.register(() => new Promise<boolean>((resolve) => { decide = resolve }))
    const later = vi.fn(() => true)
    guards.register(later)
    const leaving = guards.mayLeave()
    expect(later).not.toHaveBeenCalled()
    decide(false)
    expect(await leaving).toBe(false)
    expect(later).not.toHaveBeenCalled()
  })

  it("forgets a closed editor and admits a clean workspace", async () => {
    const guards = createLeaveGuards()
    const forget = guards.register(() => false)
    expect(await guards.mayLeave()).toBe(false)
    forget()
    expect(await guards.mayLeave()).toBe(true)
  })
})
