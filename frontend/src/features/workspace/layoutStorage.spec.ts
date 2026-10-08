import { describe, expect, it } from "vitest"

import { serverStorageKey } from "@/shared/servers/context"

import { PENDING_WORKSPACE_KEY, workspaceLayoutKey } from "./layoutStorage"

describe("the workspace layout key", () => {
  it("is kept per person as well as per server", () => {
    expect(workspaceLayoutKey("maksim")).toBe(serverStorageKey("dataplayer-workspace:maksim"))
    expect(workspaceLayoutKey("kostya")).not.toBe(workspaceLayoutKey("maksim"))
    expect(workspaceLayoutKey("maksim")).toBe(workspaceLayoutKey("maksim"))
  })

  it("never hands the next person the layout kept before the separation", () => {
    expect(workspaceLayoutKey("maksim")).not.toBe(serverStorageKey("dataplayer-workspace"))
    expect(workspaceLayoutKey("maksim")).not.toBe(serverStorageKey(PENDING_WORKSPACE_KEY))
  })
})
