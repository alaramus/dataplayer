import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

import { useConnectorChecksStore } from "./connectorChecks"
import type { CheckReport } from "./connectorChecks"

function report(ok: boolean, at = "2026-08-24T12:00:00Z"): CheckReport {
  return { ok, message: ok ? "Connected" : "Refused", latencyMs: 4, checkedAt: at }
}

describe("what the last check said", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("knows nothing about a connection nobody checked", () => {
    expect(useConnectorChecksStore().stateOf("c1")).toBe("unknown")
  })

  it("remembers the answer, per connection", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(true))
    checks.record("c2", report(false))
    expect(checks.stateOf("c1")).toBe("ok")
    expect(checks.stateOf("c2")).toBe("failed")
  })

  it("replaces the answer rather than keeping the older one", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(false))
    checks.record("c1", report(true))
    expect(checks.stateOf("c1")).toBe("ok")
  })

  // A deleted connection can be recreated under a new id, but an id that is
  // gone must not leave a dot behind for a list that outlives it.
  it("forgets a connection that is gone", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(true))
    checks.forget("c1")
    expect(checks.stateOf("c1")).toBe("unknown")
  })

  it("keeps what the answer said, not only whether it was good", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(false, "2026-08-24T12:30:00Z"))
    expect(checks.reportOf("c1")).toEqual({
      ok: false,
      message: "Refused",
      latencyMs: 4,
      checkedAt: "2026-08-24T12:30:00Z",
    })
  })

  // The dot may not claim anything about a connection nobody is watching any
  // more: the tone for that is "unknown", and it has to be reachable.
  it("has nothing to report about a connection it never heard of", () => {
    expect(useConnectorChecksStore().reportOf("c1")).toBeNull()
  })
})

/**
 * An outage is a change from answering to not, not every bad answer: the
 * server probes every few minutes, and each probe of a connection that is
 * still down used to be a new notification about the same fact (D115).
 */
describe("outages", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("begins when a connection that answered stops, and lasts through more bad answers", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(true, "2026-08-24T12:00:00Z"))
    checks.record("c1", report(false, "2026-08-24T12:03:00Z"))
    checks.record("c1", report(false, "2026-08-24T12:06:00Z"))
    checks.record("c1", report(false, "2026-08-24T12:09:00Z"))

    expect(checks.outages).toEqual({ c1: { since: "2026-08-24T12:03:00Z" } })
    expect(checks.recoveries).toEqual([])
  })

  it("is not one for a connection that never answered", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(false, "2026-08-24T12:00:00Z"))
    checks.record("c1", report(false, "2026-08-24T12:03:00Z"))

    expect(checks.outages).toEqual({})
  })

  it("ends once, with one recovery, when the connection answers again", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(true, "2026-08-24T12:00:00Z"))
    checks.record("c1", report(false, "2026-08-24T12:03:00Z"))
    checks.record("c1", report(true, "2026-08-24T12:06:00Z"))
    checks.record("c1", report(true, "2026-08-24T12:09:00Z"))

    expect(checks.outages).toEqual({})
    expect(checks.recoveries).toEqual([{ connectorId: "c1", at: "2026-08-24T12:06:00Z" }])
  })

  it("remembers a connection answered across a pause in the probes", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(true, "2026-08-24T12:00:00Z"))
    checks.clear()
    checks.record("c1", report(false, "2026-08-24T13:00:00Z"))

    expect(checks.outages).toEqual({ c1: { since: "2026-08-24T13:00:00Z" } })
  })

  it("forgets the outage of a connection that is gone", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", report(true))
    checks.record("c1", report(false))
    checks.forget("c1")

    expect(checks.outages).toEqual({})
  })
})
