import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, nextTick, ref } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import Graph3D from "./Graph3D.vue"
import { deliveryGraph } from "./fixtures"

const mock = vi.hoisted(() => ({
  fail: false, setGraph: vi.fn(), setPositions: vi.fn(), setSelection: vi.fn(), setLabels: vi.fn(),
  fit: vi.fn(), restoreCamera: vi.fn(), setActive: vi.fn(), dispose: vi.fn(),
}))
vi.mock("./scene3d", () => ({ GraphScene: class {
  constructor() { if (mock.fail) throw new Error("WebGL unavailable") }
  setGraph = mock.setGraph
  setPositions = mock.setPositions
  setSelection = mock.setSelection
  setLabels = mock.setLabels
  fit = mock.fit
  restoreCamera = mock.restoreCamera
  setActive = mock.setActive
  dispose = mock.dispose
} }))
beforeEach(() => { vi.clearAllMocks(); mock.fail = false })
const props = { graph: deliveryGraph, positions: { api: { x: 0, y: 0, z: 0 }, worker: { x: 200, y: 0, z: 0 }, monitor: { x: 0, y: 200, z: 0 } }, camera: null, selection: null, labels: true }

describe("3D scene ownership", () => {
  it("pauses when a tab is hidden and disposes when its cached panel is removed", async () => {
    const visible = ref(true)
    const wrapper = mount(defineComponent({
      components: { Graph3D }, setup: () => ({ visible, props }),
      template: '<KeepAlive><Graph3D v-if="visible" v-bind="props" /></KeepAlive>',
    }))
    expect(mock.setGraph).toHaveBeenCalledWith(deliveryGraph, props.positions)
    visible.value = false
    await wrapper.vm.$nextTick()
    expect(mock.setActive).toHaveBeenLastCalledWith(false)
    expect(mock.dispose).not.toHaveBeenCalled()
    visible.value = true
    await wrapper.vm.$nextTick()
    expect(mock.setActive).toHaveBeenLastCalledWith(true)
    wrapper.unmount()
    expect(mock.dispose).toHaveBeenCalledTimes(1)
  })

  it("shows a recoverable message if the browser cannot create a WebGL scene", async () => {
    mock.fail = true
    const wrapper = mount(Graph3D, { props, global: { plugins: [Quasar] } })
    // The scene is built in onMounted, so the banner appears one tick later.
    await nextTick()
    expect(wrapper.get('[data-testid="graph-3d-unavailable"]').text()).toContain("continue in 2D")
    wrapper.unmount()
  })
})
