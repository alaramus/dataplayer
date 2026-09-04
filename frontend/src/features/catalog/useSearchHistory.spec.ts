import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { effectScope, ref } from "vue"
import type { EffectScope } from "vue"

import { useSearchHistory } from "./useSearchHistory"

let scope: EffectScope
beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  scope = effectScope()
})
afterEach(() => scope.stop())

function setup() {
  const userId = ref<string | null>("alice")
  const connectorId = ref("files")
  const filter = ref("")
  const history = scope.run(() => useSearchHistory(userId, connectorId, filter))
  if (history === undefined) throw new Error("The test scope must be active")
  return { history, userId, connectorId, filter }
}

describe("remembering a catalog filter", () => {
  it("saves the final edit on blur rather than each intermediate keystroke", () => {
    const { history, filter } = setup()
    filter.value = "n"
    filter.value = "no"
    filter.value = "notes"
    expect(history.entries.value).toEqual([])

    history.remember()
    expect(history.entries.value).toEqual(["notes"])
    filter.value = "reports"
    history.remember(true)
    history.select("notes")
    expect(filter.value).toBe("notes")
    expect(history.entries.value).toEqual(["notes", "reports"])
  })

  it("does not put a deleted query back when the unchanged field loses focus", () => {
    const { history, filter } = setup()
    filter.value = "notes"
    history.remember()
    history.remove("notes")
    history.remember()
    expect(filter.value).toBe("notes")
    expect(history.entries.value).toEqual([])

    // Explicitly asking for the same query again is a new use of it.
    history.remember(true)
    expect(history.entries.value).toEqual(["notes"])
  })

  it("does not carry a pending edit across a connector or account change", () => {
    const { history, connectorId, userId, filter } = setup()
    filter.value = "notes"
    history.remember()
    filter.value = "unfinished"
    connectorId.value = "database"
    history.remember()
    expect(history.entries.value).toEqual([])

    filter.value = "orders"
    history.remember()
    userId.value = "bob"
    history.remember()
    expect(history.entries.value).toEqual([])
    userId.value = null
    history.remember(true)
    expect(history.entries.value).toEqual([])

    userId.value = "alice"
    expect(history.entries.value).toEqual(["orders"])
    connectorId.value = "files"
    expect(history.entries.value).toEqual(["notes"])
  })
})
