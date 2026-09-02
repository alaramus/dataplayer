import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

import { useSourceChangesStore } from "./sourceChanges"

describe("source changes", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("says nothing about a connection nothing has changed", () => {
    expect(useSourceChangesStore().lastChange("c1")).toBe(0)
  })

  it("raises a moment for the connection that changed, and no other", () => {
    const changes = useSourceChangesStore()

    changes.announce("c1")

    expect(changes.lastChange("c1")).toBeGreaterThan(0)
    expect(changes.lastChange("c2")).toBe(0)
  })
})
