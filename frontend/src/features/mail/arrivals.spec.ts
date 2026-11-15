import { describe, expect, it } from "vitest"

import { arrivalText } from "./arrivals"

describe("a new letter's notification", () => {
  const base = { connector_id: "c1", unseen: 3 }

  it("says nothing when nothing arrived", () => {
    expect(arrivalText({ ...base, count: 0, newest: [] }, "Work")).toBeNull()
  })

  it("names the sender and subject of one letter", () => {
    const text = arrivalText(
      { ...base, count: 1, newest: [{ subject: "Lunch?", sender: { name: "Bob", address: "bob@example.com" } }] },
      "Work"
    )
    expect(text).toBe("Work: Bob — Lunch?")
  })

  it("counts several", () => {
    const text = arrivalText({ ...base, count: 4, newest: [] }, "Work")
    expect(text).toBe("4 new letters in Work")
  })
})
