import { QueryClient } from "@tanstack/vue-query"
import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { CopiesService } from "@/client"
import { copyText, onCopied } from "@/shared/clipboard"
import { useAuthStore } from "@/stores/auth"

import { recordCopies } from "./record"

describe("recording copies in the history (D460)", () => {
  beforeEach(() => {
    // The store reads its token from storage, where the previous case left one.
    localStorage.clear()
    setActivePinia(createPinia())
    vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
  })

  afterEach(() => {
    onCopied(null)
    vi.restoreAllMocks()
  })

  it("sends what was copied, at most one character past what the server keeps", async () => {
    useAuthStore().setToken("token")
    const recorded = vi.spyOn(CopiesService, "recordCopy").mockResolvedValue({} as never)
    recordCopies(new QueryClient())

    await copyText("x".repeat(70_000), { from: "grid", detail: "d".repeat(300) })

    const body = recorded.mock.calls[0]![0].body
    expect(body.text).toHaveLength(65_537)
    expect(body.source).toBe("grid")
    expect(body.detail).toHaveLength(200)
  })

  it("sends nothing for a secret or for somebody not signed in", async () => {
    const recorded = vi.spyOn(CopiesService, "recordCopy").mockResolvedValue({} as never)
    recordCopies(new QueryClient())

    await copyText("before signing in", { from: "grid" })
    useAuthStore().setToken("token")
    await copyText("hunter2", { secret: true })

    expect(recorded).not.toHaveBeenCalled()
  })

  it("keeps the copy on the clipboard when the history is away", async () => {
    useAuthStore().setToken("token")
    vi.spyOn(CopiesService, "recordCopy").mockRejectedValue(new Error("offline"))
    recordCopies(new QueryClient())

    await expect(copyText("still copied", { from: "log" })).resolves.toBeUndefined()
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("still copied")
  })
})
