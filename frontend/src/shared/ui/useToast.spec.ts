import { afterEach, describe, expect, it, vi } from "vitest"

import { notices, resetNotices } from "@/shared/notifications"
import { useToast } from "./useToast"

/**
 * Which messages stay on screen, which is the one thing the four functions
 * decide differently (D114).
 */
describe("what a screen says", () => {
  afterEach(() => { resetNotices() })

  it("lets news go and keeps a failure", () => {
    const toast = useToast()

    toast.success("Row inserted")
    toast.info("Left to the source: tag_id")
    toast.error("Could not paste those cells")

    const kept = new Map(notices().entries.value.map((entry) => [entry.message, entry.sticky]))
    expect(kept.get("Row inserted")).toBe(false)
    expect(kept.get("Left to the source: tag_id")).toBe(false)
    expect(kept.get("Could not paste those cells")).toBe(true)
  })

  it("lets an offer go too, because the sheet still holds what is waiting", () => {
    // It used to stay until dismissed, when a missed card meant a missed
    // request. The first section of the sheet is that request's home now
    // (D113), so a card that never leaves is an interruption saying nothing
    // new.
    const toast = useToast()

    toast.offer("Ivan is asking for access to prod-db", { label: "Open", onClick: vi.fn() })

    const [entry] = notices().entries.value
    expect(entry?.sticky).toBe(false)
    expect(entry?.action?.label).toBe("Open")
  })

  it("carries the way to act on it", () => {
    const onClick = vi.fn()
    useToast().offer("Ivan is asking for access to prod-db", { label: "Open", onClick })

    notices().entries.value[0]?.action?.run()

    expect(onClick).toHaveBeenCalled()
  })
})
