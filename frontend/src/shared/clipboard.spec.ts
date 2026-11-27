import { afterEach, describe, expect, it, vi } from "vitest"

import { ClipboardUnavailable, copyText, onCopied, readText } from "./clipboard"

describe("application clipboard", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("writes text through one browser boundary", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()

    await copyText("copied text", { from: "grid" })

    expect(writeText).toHaveBeenCalledWith("copied text")
  })

  describe("the copy history (D460)", () => {
    afterEach(() => {
      onCopied(null)
    })

    it("hears of a copy with where it came from, after the browser took it", async () => {
      vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
      const heard = vi.fn()
      onCopied(heard)

      await copyText("SELECT 1", { from: "code", detail: "orders" })

      expect(heard).toHaveBeenCalledWith("SELECT 1", { from: "code", detail: "orders" })
    })

    it("never hears of a copy taken from the history itself", async () => {
      vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
      const heard = vi.fn()
      onCopied(heard)

      await copyText("SELECT 1", { history: true })

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("SELECT 1")
      expect(heard).not.toHaveBeenCalled()
    })

    it("never hears of a secret, an empty copy or one the browser refused", async () => {
      const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
      const heard = vi.fn()
      onCopied(heard)

      await copyText("hunter2", { secret: true })
      await copyText("", { from: "grid" })
      writeText.mockRejectedValueOnce(new Error("denied"))
      await expect(copyText("refused", { from: "grid" })).rejects.toThrow()

      expect(heard).not.toHaveBeenCalled()
    })
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

      await copyText("over http", { from: "grid" })

      expect(document.execCommand).toHaveBeenCalledWith("copy")
      expect(selected).toBe("over http")
      expect(document.querySelector("textarea")).toBeNull()
    })

    it("fails when the browser refuses that copy too", async () => {
      withoutClipboard()
      document.execCommand = vi.fn(() => false)

      await expect(copyText("refused", { from: "grid" })).rejects.toThrow()
    })

    it("says it cannot read rather than failing on undefined", async () => {
      withoutClipboard()

      await expect(readText()).rejects.toBeInstanceOf(ClipboardUnavailable)
    })
  })
})
