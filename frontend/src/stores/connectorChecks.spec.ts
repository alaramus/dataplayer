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
