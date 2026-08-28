import { describe, expect, it, vi } from "vitest"

import { copyText } from "./clipboard"

describe("application clipboard", () => {
  it("writes text through one browser boundary", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()

    await copyText("copied text")

    expect(writeText).toHaveBeenCalledWith("copied text")
  })
})
