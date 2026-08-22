import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

import { useConnectorChecksStore } from "./connectorChecks"

describe("what the last check said", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("knows nothing about a connection nobody checked", () => {
    expect(useConnectorChecksStore().stateOf("c1")).toBe("unknown")
  })

  it("remembers the answer, per connection", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", true)
    checks.record("c2", false)
    expect(checks.stateOf("c1")).toBe("ok")
    expect(checks.stateOf("c2")).toBe("failed")
  })

  it("replaces the answer rather than keeping the older one", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", false)
    checks.record("c1", true)
    expect(checks.stateOf("c1")).toBe("ok")
  })

  // A deleted connection can be recreated under a new id, but an id that is
  // gone must not leave a dot behind for a list that outlives it.
  it("forgets a connection that is gone", () => {
    const checks = useConnectorChecksStore()
    checks.record("c1", true)
    checks.forget("c1")
    expect(checks.stateOf("c1")).toBe("unknown")
  })
})
