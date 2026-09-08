import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { AxiosError, AxiosHeaders } from "axios"
import { Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import type { SourceFeature, SourceFeatures } from "@/client"
import ConnectorFeatures from "@/features/connectors/ConnectorFeatures.vue"
import { sourceFeaturesKey } from "@/features/connectors/features"

const read = vi.hoisted(() => vi.fn())
vi.mock("@/client", () => ({ ConnectorsService: { readSourceFeatures: read } }))

const cleanup: (() => void)[] = []

function answer(state: SourceFeature["state"], version = "2.18.0"): SourceFeatures {
  return {
    observed_at: "2026-09-08T12:00:00Z",
    features: [{
      code: "timescaledb", title: "TimescaleDB", state,
      installed_version: state === "absent" ? null : version,
      reason: state === "unsupported" || state === "unavailable" ? "Public metadata is unavailable" : null,
    }],
  }
}

function failure(status: number) {
  return new AxiosError("Request failed", undefined, undefined, undefined, {
    status, statusText: "Refused", data: {}, headers: {}, config: { headers: new AxiosHeaders() },
  })
}

function panel(connectorId = "c1", client = new QueryClient()) {
  const wrapper = mount(ConnectorFeatures, {
    props: { connectorId },
    global: { plugins: [Quasar, [VueQueryPlugin, { queryClient: client }]] },
  })
  cleanup.push(() => {
    wrapper.unmount()
    client.clear()
  })
  return { wrapper, client }
}

beforeEach(() => { read.mockReset() })
afterEach(() => { cleanup.splice(0).forEach((close) => close()) })

describe("detected source features", () => {
  it.each([
    ["available", "Available for inspection"],
    ["absent", "Not installed"],
    ["unsupported", "Unsupported inspection API"],
    ["unavailable", "Inspection unavailable"],
  ] as const)("shows %s distinctly", async (state, label) => {
    read.mockResolvedValue({ data: answer(state) })
    const { wrapper } = panel()
    await flushPromises()
    expect(wrapper.text()).toContain(label)
    expect(wrapper.text().includes("2.18.0")).toBe(state !== "absent")
    if (state === "unsupported" || state === "unavailable") {
      expect(wrapper.text()).toContain("Public metadata is unavailable")
    }
    expect(read).toHaveBeenCalledWith({ path: { connector_id: "c1" } })
  })

  it("reloads extension removal without keeping the old version", async () => {
    read.mockResolvedValueOnce({ data: answer("available") })
      .mockResolvedValueOnce({ data: answer("absent") })
    const { wrapper } = panel()
    await flushPromises()
    await wrapper.get('[data-testid="reload-source-features"]').trigger("click")
    await flushPromises()
    expect(wrapper.text()).toContain("Not installed")
    expect(wrapper.text()).not.toContain("2.18.0")
    expect(read).toHaveBeenCalledTimes(2)
  })

  it.each([403, 404, 500])("replaces stale detection with an error after HTTP %s", async (status) => {
    read.mockResolvedValueOnce({ data: answer("available") }).mockRejectedValueOnce(failure(status))
    const { wrapper } = panel()
    await flushPromises()
    await wrapper.get('[data-testid="reload-source-features"]').trigger("click")
    await flushPromises()
    expect(wrapper.find('[data-testid="source-features-error"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain("Available for inspection")
    expect(wrapper.text()).not.toContain("Not installed")
    expect(read).toHaveBeenCalledTimes(2)
  })

  it("hides the section only for an unsupported capability", async () => {
    read.mockRejectedValue(failure(501))
    const { wrapper } = panel()
    await flushPromises()
    expect(wrapper.find('[data-testid="connector-features"]').exists()).toBe(false)
    expect(read).toHaveBeenCalledOnce()
  })

  it("keeps two databases independent and refreshes only the invalidated answer", async () => {
    read.mockImplementation(async ({ path }: { path: { connector_id: string } }) => ({
      data: answer(path.connector_id === "c1" ? "available" : "absent"),
    }))
    const client = new QueryClient()
    const first = panel("c1", client)
    const second = panel("c2", client)
    await flushPromises()
    expect(first.wrapper.text()).toContain("2.18.0")
    expect(second.wrapper.text()).toContain("Not installed")
    read.mockResolvedValue({ data: answer("available", "2.19.0") })
    await client.invalidateQueries({ queryKey: sourceFeaturesKey("c1") })
    await flushPromises()
    expect(first.wrapper.text()).toContain("2.19.0")
    expect(second.wrapper.text()).toContain("Not installed")
    expect(read).toHaveBeenCalledTimes(3)
  })
})
