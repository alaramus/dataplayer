import { describe, expect, it } from "vitest"

import { staleChecks } from "@/features/connectors/health"

describe("which results the dot may no longer show", () => {
  it("keeps what is known about a connection that is still on", () => {
    expect(staleChecks(["c1"], [{ id: "c1", enabled: true }])).toEqual([])
  })

  it("drops a connection that is gone", () => {
    expect(staleChecks(["c1"], [])).toEqual(["c1"])
  })

  // The server stops probing a switched-off connection, so the last thing it
  // said stops being true of it. The dot has its own tone for "off", and a
  // green one underneath would be a claim nobody is checking.
  it("drops a connection that was switched off", () => {
    expect(staleChecks(["c1"], [{ id: "c1", enabled: false }])).toEqual(["c1"])
  })

  it("says nothing about a connection nothing is known about", () => {
    expect(staleChecks([], [{ id: "c1", enabled: false }])).toEqual([])
  })
})
