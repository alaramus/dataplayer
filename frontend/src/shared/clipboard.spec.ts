import { afterEach, describe, expect, it, vi } from "vitest"

import { ClipboardUnavailable, copyText, readText } from "./clipboard"

describe("application clipboard", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("writes text through one browser boundary", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()

    await copyText("copied text")

    expect(writeText).toHaveBeenCalledWith("copied text")
  })

  describe("outside a secure context", () => {
    const original = Object.getOwnPropertyDescriptor(navigator, "clipboard")
    afterEach(() => {
      if (original) Object.defineProperty(navigator, "clipboard", original)
    })

    function withoutClipboard() {
      Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined })
    }

    it("copies through a selection", async () => {
      withoutClipboard()
      let selected = ""
      document.execCommand = vi.fn(() => {
        selected = document.querySelector("textarea")?.value ?? ""
        return true
      })

      await copyText("over http")

      expect(document.execCommand).toHaveBeenCalledWith("copy")
      expect(selected).toBe("over http")
      expect(document.querySelector("textarea")).toBeNull()
    })

    it("fails when the browser refuses that copy too", async () => {
      withoutClipboard()
      document.execCommand = vi.fn(() => false)

      await expect(copyText("refused")).rejects.toThrow()
    })

    it("says it cannot read rather than failing on undefined", async () => {
      withoutClipboard()

      await expect(readText()).rejects.toBeInstanceOf(ClipboardUnavailable)
    })
  })
})
