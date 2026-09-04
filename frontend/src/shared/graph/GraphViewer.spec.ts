import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, ref } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import GraphViewer from "./GraphViewer.vue"
import { deliveryGraph } from "./fixtures"
import { arrange } from "./layout"
import { emptyGraphView } from "./viewState"
import type { GraphDocument } from "./model"

// WebGL picking is exercised in Playwright. Here the alternate renderer is a
// boundary: selection must survive replacing either presentation component.
vi.mock("./Graph3D.vue", () => ({ default: {
  props: ["selection"],
  template: '<div data-testid="alternate-view">{{ selection?.id }}</div>',
} }))

class LayoutWorker {
  static instances: LayoutWorker[] = []
  onmessage?: (event: { data: { result: ReturnType<typeof arrange> } }) => void
  onerror?: () => void
  terminate = vi.fn()
  request?: { graph: GraphDocument; expanded: boolean }
  constructor() { LayoutWorker.instances.push(this) }
  postMessage(request: { graph: GraphDocument; expanded: boolean }) { this.request = request }
  complete() { this.onmessage?.({ data: { result: arrange(this.request!.graph, this.request!.expanded) } }) }
}

beforeEach(() => {
  LayoutWorker.instances = []
  vi.stubGlobal("Worker", LayoutWorker)
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} })
})
afterEach(() => vi.unstubAllGlobals())

function mountViewer() {
  return mount(defineComponent({
    components: { GraphViewer },
    setup: () => ({ graph: deliveryGraph, view: ref(emptyGraphView()) }),
    template: '<GraphViewer v-model="view" :graph="graph" />',
  }), { global: { plugins: [Quasar] } })
}

describe("the shared graph viewer", () => {
  it("shows a non-table graph, its ports and shared selection in both presentations", async () => {
    const wrapper = mountViewer()
    LayoutWorker.instances[0]!.complete()
    await flushPromises()
    await wrapper.get('[data-testid="graph-port-api-events"]').trigger("click")
    const inspector = wrapper.get('[data-testid="graph-inspector"]')
    expect(inspector.text()).toContain("Gateway")
    expect(inspector.text()).toContain("Dispatch jobs")
    expect(inspector.text()).not.toContain("Observe")
    await wrapper.get('[data-testid="graph-mode-3d"]').trigger("click")
    await flushPromises()
    expect(wrapper.get('[data-testid="alternate-view"]').text()).toBe("api")
    expect(wrapper.get('[data-testid="graph-inspector"]').text()).toContain("Gateway")
    await wrapper.get('[data-testid="graph-mode-2d"]').trigger("click")
    await flushPromises()
    expect(wrapper.get('[data-testid="graph-port-api-events"]').exists()).toBe(true)
    wrapper.unmount()
    expect(LayoutWorker.instances[0]!.terminate).toHaveBeenCalled()
  })

  it("reports worker failure and lets Arrange retry", async () => {
    const wrapper = mountViewer()
    LayoutWorker.instances[0]!.onerror?.()
    await flushPromises()
    expect(wrapper.get('[data-testid="graph-error"]').text()).toContain("could not be arranged")
    await wrapper.get('[data-testid="graph-arrange"]').trigger("click")
    LayoutWorker.instances[1]!.complete()
    await flushPromises()
    expect(wrapper.find('[data-testid="graph-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="graph-node-api"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
