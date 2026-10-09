import { describe, expect, it } from "vitest"

import { serverStorageKey } from "@/shared/servers/context"

import { forgetSharedLayouts, workspaceLayoutKey } from "./layoutStorage"

describe("the workspace layout key", () => {
  it("is kept per person as well as per server", () => {
    expect(workspaceLayoutKey("maksim")).toBe(serverStorageKey("dataplayer-workspace:maksim"))
    expect(workspaceLayoutKey("kostya")).not.toBe(workspaceLayoutKey("maksim"))
    expect(workspaceLayoutKey("maksim")).toBe(workspaceLayoutKey("maksim"))
  })

  it("forgets the layouts kept for everyone and keeps each person's own", () => {
    localStorage.setItem(serverStorageKey("dataplayer-workspace"), "somebody's tabs")
    localStorage.setItem(serverStorageKey("dataplayer-workspace:pending"), "somebody's tabs")
    localStorage.setItem(workspaceLayoutKey("maksim"), "maksim's tabs")

    forgetSharedLayouts()

    expect(localStorage.getItem(serverStorageKey("dataplayer-workspace"))).toBeNull()
    expect(localStorage.getItem(serverStorageKey("dataplayer-workspace:pending"))).toBeNull()
    expect(localStorage.getItem(workspaceLayoutKey("maksim"))).toBe("maksim's tabs")
    localStorage.clear()
  })
})
