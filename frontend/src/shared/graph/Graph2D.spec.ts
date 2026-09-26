import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
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
    // An anchor only where a line arrives: the gateway sits left of both the
    // worker and the monitor, so its two connected fields are anchored on the
    // right alone, and the field no edge names is anchored nowhere.
    expect(wrapper.findAll('[data-testid="graph-anchor-api-events"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="graph-anchor-api-version"]').exists()).toBe(false)
    await wrapper.setProps({ expanded: false })
    expect(wrapper.find('[data-testid="graph-port-api-events"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="graph-edge-jobs"]').exists()).toBe(true)
    wrapper.unmount()
    expect(disconnect).toHaveBeenCalled()
  })

  it("takes a producer's commands in a card's head without them dragging or selecting it", async () => {
    const graph = {
      ...deliveryGraph,
      nodes: deliveryGraph.nodes.map((node) => node.id === "api"
        ? { ...node, rows: [{ ...node.rows[0]!, icon: "table_chart", muted: true }, ...node.rows.slice(1)] }
        : node),
    }
    const wrapper = mount(Graph2D, {
      props: { ...props, graph },
      global: { plugins: [Quasar] },
      slots: { "node-head": `<template #node-head="{ node }"><button :data-testid="'head-' + node.id">Settings</button></template>` },
    })
    const button = wrapper.get('[data-testid="head-api"]')
    pointer(button.element, "pointerdown", 100, 100)
    await button.trigger("dblclick")
    await button.trigger("keydown", { key: "Enter" })
    expect(wrapper.emitted("select")).toBeUndefined()
    expect(wrapper.emitted("activate")).toBeUndefined()
    const row = wrapper.get('[data-testid="graph-port-api-events"]')
    expect(row.classes()).toContain("graph-node__row--muted")
    expect(row.find(".q-icon").exists()).toBe(true)
    expect(wrapper.get('[data-testid="graph-port-api-metrics"]').classes()).not.toContain("graph-node__row--muted")
    // A selection fades what it does not touch, unless the producer says not.
    await wrapper.setProps({ selection: { kind: "node", id: "worker" } })
    expect(wrapper.get('[data-testid="graph-node-monitor"]').classes()).toContain("graph-2d__dim")
    await wrapper.setProps({ dimOthers: false })
    expect(wrapper.get('[data-testid="graph-node-monitor"]').classes()).not.toContain("graph-2d__dim")
    wrapper.unmount()
  })

  it("joins a row dragged onto a row of another card, and only then", async () => {
    const wrapper = mount(Graph2D, { props: { ...props, linkable: true, edgeLabels: true }, attachTo: document.body })
    const root = wrapper.get('[data-testid="graph-2d"]').element as HTMLElement
    root.getBoundingClientRect = () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600, x: 0, y: 0, toJSON: () => ({}) })
    const row = wrapper.get('[data-testid="graph-port-api-events"]').element as HTMLElement
    const aim = wrapper.get('[data-testid="graph-port-worker-input"]').element
    row.setPointerCapture = vi.fn()
    row.hasPointerCapture = () => true
    row.releasePointerCapture = vi.fn()
    const under = vi.fn(() => aim)
    Object.defineProperty(document, "elementFromPoint", { value: under, configurable: true })

    pointer(row, "pointerdown", 100, 100)
    pointer(root, "pointermove", 101, 100)
    await wrapper.vm.$nextTick()
    // A press is a press until it has moved.
    expect(wrapper.find('[data-testid="graph-draft-edge"]').exists()).toBe(false)
    pointer(root, "pointermove", 300, 120)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="graph-draft-edge"]').exists()).toBe(true)
    expect(aim.classList.contains("graph-node__row--aimed")).toBe(true)
    pointer(root, "pointerup", 300, 120)
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("connect")).toEqual([[{ nodeId: "api", portId: "events" }, { nodeId: "worker", portId: "input" }]])
    expect(wrapper.find('[data-testid="graph-draft-edge"]').exists()).toBe(false)
    // The click the drag ends with is not a selection of the row it left.
    await wrapper.get('[data-testid="graph-port-api-events"]').trigger("click")
    expect(wrapper.emitted("select")).toBeUndefined()

    // Onto its own card: nothing to join.
    under.mockReturnValue(wrapper.get('[data-testid="graph-port-api-metrics"]').element)
    pointer(row, "pointerdown", 100, 100)
    pointer(root, "pointermove", 140, 140)
    pointer(root, "pointerup", 140, 140)
    expect(wrapper.emitted("connect")).toHaveLength(1)
    // Labels are written along the edges.
    expect(wrapper.findAll(".graph-2d__label").map((label) => label.text())).toContain("Dispatch jobs")
    wrapper.unmount()
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
