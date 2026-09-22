import { describe, expect, it, vi } from "vitest"

import { openAsTabAction } from "./asTab"

describe("openAsTabAction", () => {
  it("is the window-to-tab command every such window carries (D155)", () => {
    const run = vi.fn()
    const action = openAsTabAction(run)

    expect(action.icon).toBe("tab")
    expect(action.tooltip).toBe("Open as a tab")
    expect(action.testid).toBe("window-to-tab")

    action.run()
    expect(run).toHaveBeenCalledTimes(1)
  })
})
