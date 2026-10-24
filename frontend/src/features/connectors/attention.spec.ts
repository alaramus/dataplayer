import { createPinia, setActivePinia } from "pinia"
import { computed, effectScope, nextTick } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useConnectorChecksStore } from "@/stores/connectorChecks"

import { useHealthAttention } from "./attention"

const success = vi.fn()

vi.mock("@/features/connectors/api", () => ({
  useConnectors: () => ({ data: computed(() => ({ data: [{ id: "c1", name: "redis-cache" }] })) }),
}))
vi.mock("@/shared/ui", async (original) => ({
  ...(await original<typeof import("@/shared/ui")>()),
  useToast: () => ({ success, error: vi.fn(), info: vi.fn(), warning: vi.fn() }),
}))

function at(minute: number): string {
  return `2026-10-24T12:${String(minute).padStart(2, "0")}:00Z`
}

function probe(ok: boolean, minute: number) {
  useConnectorChecksStore().record("c1", {
    ok,
    message: ok ? "Connected" : "Redis is unavailable",
    latencyMs: null,
    checkedAt: at(minute),
  })
}

describe("a connection that stopped answering, as something waiting for a person (D115)", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    success.mockClear()
  })

  it("is one item for the whole outage, however often it is probed", async () => {
    const scope = effectScope()
    const items = scope.run(() => useHealthAttention(() => undefined))
    probe(true, 0)
    probe(false, 3)
    const first = items?.value.map((item) => item.id)
    probe(false, 6)
    probe(false, 9)
    await nextTick()

    expect(first).toEqual([`check:c1:${at(3)}`])
    expect(items?.value.map((item) => item.id)).toEqual(first)
    expect(items?.value[0]?.detail).toBe("Redis is unavailable")
    scope.stop()
  })

  it("says nothing about a connection that has not answered since the tab opened", async () => {
    const scope = effectScope()
    const items = scope.run(() => useHealthAttention(() => undefined))
    probe(false, 0)
    probe(false, 3)
    await nextTick()

    expect(items?.value).toEqual([])
    scope.stop()
  })

  it("goes away when the connection answers again, said once in Recent", async () => {
    const scope = effectScope()
    const items = scope.run(() => useHealthAttention(() => undefined))
    probe(true, 0)
    probe(false, 3)
    await nextTick()
    probe(true, 6)
    await nextTick()
    probe(true, 9)
    await nextTick()

    expect(items?.value).toEqual([])
    expect(success).toHaveBeenCalledTimes(1)
    expect(success).toHaveBeenCalledWith("redis-cache is answering again")
    scope.stop()
  })
})
