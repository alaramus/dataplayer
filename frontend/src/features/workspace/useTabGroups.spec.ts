import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ref } from "vue"

import type { ConfirmRequest } from "@/shared/ui"
import type { RestoreOutcome } from "@/shared/workspace"

import { groupsKey, groupWarningKey } from "./groups"
import { groupFixture } from "./testing/tabGroups"
import { useTabGroups } from "./useTabGroups"

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

function fixture(userId = "user-one") {
  const workspace = {
    panels: ref(groupFixture().panels),
    snapshot: vi.fn(() => groupFixture().snapshot),
    restore: vi.fn<(raw: string) => Promise<RestoreOutcome>>().mockResolvedValue("restored"),
  }
  const confirm = vi.fn<(request: ConfirmRequest) => Promise<boolean>>().mockResolvedValue(true)
  const toast = { success: vi.fn(), info: vi.fn(), error: vi.fn(), offer: vi.fn() }
  return { workspace, confirm, toast, library: useTabGroups(userId, workspace, confirm, toast) }
}

describe("the user's tab group library", () => {
  it("keeps saved copies until explicitly updated and preserves them on rename", () => {
    const { library } = fixture()
    expect(library.save(" Queries ")).toBe(true)
    const original = library.groups.value[0]!
    expect(library.save("Second group")).toBe(true)
    expect(library.groups.value[0]).toEqual(original)
    expect(library.rename(original.id, "Work")).toBe(true)
    expect(library.groups.value[0]?.snapshot).toBe(original.snapshot)
    expect(library.update(original.id)).toBe(true)
    expect(library.groups.value[0]?.snapshot).toBe(original.snapshot)
    expect(fixture().library.groups.value).toEqual(library.groups.value)
  })

  it("does not save or update groups when only the permanent connectors tab is open", () => {
    const { library, workspace } = fixture()
    expect(library.save("Queries")).toBe(true)
    const original = library.groups.value[0]!
    workspace.panels.value = groupFixture(false).panels
    workspace.snapshot.mockReturnValue(groupFixture(false).snapshot)

    expect(library.canSave.value).toBe(false)
    expect(library.save("Empty")).toBe(false)
    expect(library.update(original.id)).toBe(false)
    expect(library.groups.value).toEqual([original])
    expect(workspace.snapshot).toHaveBeenCalledTimes(1)
  })

  it("separates users and never lets deleting a saved group close current tabs", async () => {
    const { library, workspace } = fixture()
    library.save("Queries")
    expect(fixture("user-two").library.groups.value).toEqual([])
    await library.remove(library.groups.value[0]!)
    expect(library.groups.value).toEqual([])
    expect(workspace.restore).not.toHaveBeenCalled()
  })

  it("leaves groups intact when deletion is declined", async () => {
    const { library, confirm } = fixture()
    library.save("Queries")
    confirm.mockResolvedValue(false)
    await library.remove(library.groups.value[0]!)
    expect(library.groups.value).toHaveLength(1)
  })

  it("does not replace tabs or remember anything when the warning is cancelled", async () => {
    const { library, confirm, workspace } = fixture()
    library.save("Queries")
    confirm.mockResolvedValue(false)
    await library.open(library.groups.value[0]!)
    expect(workspace.restore).not.toHaveBeenCalled()
    expect(localStorage.getItem(groupWarningKey("user-one"))).toBeNull()
    expect(library.busy.value).toBe(false)
  })

  it("asks again unless Don't show again was accepted, including after reload", async () => {
    const { library, confirm, workspace } = fixture()
    library.save("Queries")
    const group = library.groups.value[0]!
    await library.open(group)
    await library.open(group)
    expect(confirm).toHaveBeenCalledTimes(2)
    confirm.mockImplementation(async (request) => { request.onRemember?.(); return true })
    await library.open(group)
    expect(localStorage.getItem(groupWarningKey("user-one"))).toBe("true")
    const reloaded = fixture()
    // The engine still receives the request and retains its close guards.
    reloaded.workspace.restore.mockResolvedValue("cancelled")
    await reloaded.library.open(group)
    expect(reloaded.confirm).not.toHaveBeenCalled()
    expect(reloaded.workspace.restore).toHaveBeenCalledWith(group.snapshot)
    expect(workspace.restore).toHaveBeenCalledTimes(3)
  })

  it("reports a failed write and retains the previous saved copy", () => {
    const { library, workspace, toast } = fixture()
    library.save("Queries")
    const original = library.groups.value[0]!
    const saved = localStorage.getItem(groupsKey("user-one"))
    workspace.snapshot.mockReturnValue(groupFixture(false).snapshot)
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota") })
    expect(library.update(original.id)).toBe(false)
    expect(library.groups.value[0]).toEqual(original)
    expect(localStorage.getItem(groupsKey("user-one"))).toBe(saved)
    expect(toast.error).toHaveBeenCalled()
  })

  it("does not open two replacement questions at once", async () => {
    const { library, confirm, workspace } = fixture()
    library.save("Queries")
    let answer: (allowed: boolean) => void = () => { throw new Error("No question") }
    confirm.mockImplementation(() => new Promise<boolean>((resolve) => { answer = resolve }))
    const group = library.groups.value[0]!
    const opening = library.open(group)
    await library.open(group)
    expect(confirm).toHaveBeenCalledTimes(1)
    answer(true)
    await opening
    expect(workspace.restore).toHaveBeenCalledTimes(1)
  })
})
