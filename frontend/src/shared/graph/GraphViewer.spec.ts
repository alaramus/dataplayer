import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, ref } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import GraphViewer from "./GraphViewer.vue"
import { deliveryGraph } from "./fixtures"
import { arrange } from "./layout"
import { emptyGraphView } from "./viewState"
import type { GraphDocument, GraphViewState, Point3 } from "./model"

// WebGL picking is exercised in Playwright. Here the alternate renderer is a
// boundary: selection must survive replacing either presentation component.
// __esModule: the viewer loads this one through defineAsyncComponent, which
// unwraps `default` only from something that says it is a module.
vi.mock("./Graph3D.vue", () => ({ __esModule: true, default: {
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

function mountViewer(view = ref<GraphViewState>(emptyGraphView())) {
  return mount(defineComponent({
    components: { GraphViewer },
    setup: () => ({ graph: deliveryGraph, view }),
    template: '<GraphViewer v-model="view" :graph="graph" />',
  }), { global: { plugins: [Quasar] } })
}

describe("the shared graph viewer", () => {
  it("upgrades untouched flat 3D positions while keeping manual edits", async () => {
    const first = arrange(deliveryGraph, true)
    const groups = [...new Set(deliveryGraph.nodes.map((node) => node.groupId ?? ""))].sort()
    const flat: Record<string, Point3> = Object.fromEntries(deliveryGraph.nodes.map((node) => [
      node.id, {
        x: first.positions2[node.id]!.x * 0.7,
        y: groups.indexOf(node.groupId ?? "") * 180,
        z: first.positions2[node.id]!.y * 0.55,
      },
    ]))
    const view = ref<GraphViewState>({
      ...emptyGraphView(), positions2: first.positions2, positions3: flat,
    })
    const wrapper = mountViewer(view)
    LayoutWorker.instances[0]!.complete()
    await flushPromises()

    expect(view.value.positions3).toEqual(first.positions3)
    expect(view.value.positions2).toEqual(first.positions2)
    wrapper.unmount()

    const moved = { ...flat, api: { ...flat.api!, y: flat.api!.y + 20 } }
    const manual = ref<GraphViewState>({
      ...emptyGraphView(), positions2: first.positions2, positions3: moved,
    })
    const second = mountViewer(manual)
    LayoutWorker.instances[1]!.complete()
    await flushPromises()

    expect(manual.value.positions3).toEqual(moved)
    second.unmount()
  })

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
    expect(wrapper.find('[data-testid="graph-port-api-events"]').exists()).toBe(true)
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
