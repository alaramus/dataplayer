import { mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { afterEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"

import ConnectorIcon from "./ConnectorIcon.vue"
import { useConnectorChecksStore } from "@/stores/connectorChecks"

describe("connection icon tooltip", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("updates the age while the last check stays the same", async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-08-24T12:00:00Z"))
    const pinia = createPinia()
    setActivePinia(pinia)
    useConnectorChecksStore().record("c1", {
      ok: true,
      message: "Connected",
      latencyMs: 4,
      checkedAt: "2026-08-24T12:00:00Z",
    })

    const wrapper = mount(ConnectorIcon, {
      props: {
        connectorId: "c1",
        name: "Demo",
        adapterType: "postgres",
        tooltip: "Edit connection",
        testid: "connector-edit-Demo",
      },
      global: {
        plugins: [pinia],
        stubs: {
          AppIconButton: { props: ["tooltip"], template: '<button :title="tooltip" />' },
          ConnectorDot: true,
        },
      },
    })

    expect(wrapper.get("button").attributes("title")).toContain("0s ago")
    await vi.advanceTimersByTimeAsync(30_000)
    await nextTick()
    expect(wrapper.get("button").attributes("title")).toContain("30s ago")
    wrapper.unmount()
  })
})
