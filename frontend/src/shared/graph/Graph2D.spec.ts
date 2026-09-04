import { mount } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import Graph2D from "./Graph2D.vue"
import { deliveryGraph } from "./fixtures"

const props = {
  graph: deliveryGraph, positions: { api: { x: 10, y: 20 }, worker: { x: 500, y: 20 }, monitor: { x: 900, y: 20 } },
  camera: { x: 0, y: 0, zoom: 0.5 }, expanded: true, selection: null,
}
const disconnect = vi.fn()
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect = disconnect })
})
afterEach(() => vi.unstubAllGlobals())

function pointer(element: Element, type: string, x: number, y: number) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y })
  Object.defineProperties(event, { pointerId: { value: 1 }, isPrimary: { value: true } })
  element.dispatchEvent(event)
}

describe("the generic 2D canvas", () => {
  it("selects a port and its connection from the keyboard, and activates a node", async () => {
    const wrapper = mount(Graph2D, { props })
    await wrapper.get('[data-testid="graph-port-api-events"]').trigger("keydown", { key: "Enter" })
    expect(wrapper.emitted("select")!.at(-1)).toEqual([{ kind: "node", id: "api", portId: "events" }])
    await wrapper.get('[data-testid="graph-edge-jobs"]').trigger("keydown", { key: "Enter" })
    expect(wrapper.emitted("select")!.at(-1)).toEqual([{ kind: "edge", id: "jobs" }])
    await wrapper.get('[aria-label="Gateway"]').trigger("dblclick")
    expect(wrapper.emitted("activate")).toEqual([["api"]])
    await wrapper.setProps({ expanded: false })
    expect(wrapper.find('[data-testid="graph-port-api-events"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="graph-edge-jobs"]').exists()).toBe(true)
    wrapper.unmount()
    expect(disconnect).toHaveBeenCalled()
  })

  it("moves in world coordinates and restores the original position on Escape", async () => {
    const wrapper = mount(Graph2D, { props })
    const root = wrapper.get('[data-testid="graph-2d"]')
    const head = wrapper.get('[aria-label="Gateway"]').element as HTMLElement
    head.setPointerCapture = vi.fn()
    head.hasPointerCapture = () => true
    head.releasePointerCapture = vi.fn()
    pointer(head, "pointerdown", 100, 100)
    pointer(root.element, "pointermove", 140, 120)
    expect(wrapper.emitted("move")!.at(-1)).toEqual(["api", { x: 90, y: 60 }])
    expect(props.positions.api).toEqual({ x: 10, y: 20 })
    await root.trigger("keydown", { key: "Escape" })
    expect(wrapper.emitted("move")!.at(-1)).toEqual(["api", { x: 10, y: 20 }])
    expect(head.releasePointerCapture).toHaveBeenCalledWith(1)
    pointer(root.element, "pointerup", 140, 120)
    expect(wrapper.emitted("select")).toBeUndefined()
    wrapper.unmount()
  })
})
