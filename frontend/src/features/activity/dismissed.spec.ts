import { describe, expect, it } from "vitest"

import { createDismissedJobs } from "./dismissed"
import { RECENT_FOR } from "./endings"

function memory(): Storage {
  const values = new Map<string, string>()
  return {
    get length() { return values.size },
    clear: () => { values.clear() },
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(key) },
    setItem: (key, value) => { values.set(key, value) },
  }
}

describe("the endings a person waved away", () => {
  it("stay away after a reload, which reads every ending from the server again", () => {
    const storage = memory()
    createDismissedJobs(storage, () => 1000).dismiss("j1")

    const reloaded = createDismissedJobs(storage, () => 2000)

    expect([...reloaded.ids.value]).toEqual(["j1"])
  })

  it("are let go once the ending could not come back anyway", () => {
    const storage = memory()
    createDismissedJobs(storage, () => 0).dismiss("j1")

    // Kept twice as long as an ending stays recent, then dropped.
    expect([...createDismissedJobs(storage, () => 2 * RECENT_FOR).ids.value]).toEqual(["j1"])
    expect([...createDismissedJobs(storage, () => 2 * RECENT_FOR + 1).ids.value]).toEqual([])
  })

  it("ignore what the browser holds under that name if it is not theirs", () => {
    for (const junk of ["not json", "[1,2]", '{"j1":"yesterday"}']) {
      const storage = memory()
      createDismissedJobs(storage).dismiss("j0")
      storage.setItem(storage.key(0) ?? "", junk)

      expect([...createDismissedJobs(storage).ids.value]).toEqual([])
    }
  })
})
