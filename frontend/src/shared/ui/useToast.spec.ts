import { afterEach, describe, expect, it, vi } from "vitest"

import { notices, resetNotices } from "@/shared/notifications"
import { useToast } from "./useToast"

/**
 * Every message goes to Activity, and a card is a temporary way to show it.
 */
describe("what a screen says", () => {
  afterEach(() => { resetNotices() })

  it("records news and failures as temporary cards", () => {
    const toast = useToast()

    toast.success("Row inserted")
    toast.info("Left to the source: tag_id")
    toast.error("Could not paste those cells")

    expect(notices().cards.value.map((entry) => entry.message)).toEqual([
      "Row inserted", "Left to the source: tag_id", "Could not paste those cells",
    ])
  })

  it("lets an offer go too, because the sheet still holds what is waiting", () => {
    // It used to stay until dismissed, when a missed card meant a missed
    // request. The first section of the sheet is that request's home now
    // (D113), so a card that never leaves is an interruption saying nothing
    // new.
    const toast = useToast()

    toast.offer("Ivan is asking for access to prod-db", { label: "Open", onClick: vi.fn() })

    const [entry] = notices().entries.value
    expect(entry?.action?.label).toBe("Open")
  })

  it("carries the way to act on it", () => {
    const onClick = vi.fn()
    useToast().offer("Ivan is asking for access to prod-db", { label: "Open", onClick })

    notices().entries.value[0]?.action?.run()

    expect(onClick).toHaveBeenCalled()
  })
})
