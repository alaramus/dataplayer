import { flushPromises, mount } from "@vue/test-utils"
import { h } from "vue"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { first } from "@/shared/testing/collections"
import { AppTooltip } from "@/shared/ui"

import TabularGrid from "./TabularGrid.vue"
import { defaultColumnLayout } from "./columnLayout"
import type { TabularColumn } from "./tabular"

const COLUMNS: TabularColumn[] = [
  {
    id: "0",
    label: "value",
    type: { sql: "text", category: "string" },
    sortable: true,
    filter_operators: ["eq"],
    editable: true,
  },
  {
    id: "1",
    label: "value",
    type: { sql: "text", category: "string" },
    sortable: true,
    filter_operators: ["eq"],
  },
]

function mountGrid(overrides: Record<string, unknown> = {}) {
  return mount(TabularGrid, {
    props: {
      columns: COLUMNS,
      rows: [{ id: "row-a", values: ["left", "right"] }],
      page: 0,
      pageSize: 100,
      filters: [],
      sort: [],
      layout: defaultColumnLayout(COLUMNS),
      ...overrides,
    },
    global: { plugins: [Quasar] },
  })
}

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: vi.fn().mockResolvedValue(undefined),
      readText: vi.fn().mockResolvedValue(""),
    },
  })
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
})

describe("the controlled tabular grid", () => {
  it("fits unsized columns to their contents and preserves an explicit width", () => {
    const wrapper = mountGrid({
      rows: [{ id: "row-a", values: ["short", "A".repeat(100)] }],
    })
    const grid = wrapper.get('[data-testid="row-grid"]').element as HTMLElement
    expect(Number.parseFloat(grid.style.getPropertyValue("--grid-column-0"))).toBeLessThan(160)
    expect(grid.style.getPropertyValue("--grid-column-1")).toBe("480px")

    const restored = mountGrid({
      layout: { ...defaultColumnLayout(COLUMNS), columnSizing: { "0": 220 } },
    })
    expect(restored.get('[data-testid="row-grid"]').attributes("style")).toContain(
      "--grid-column-0: 220px"
    )
  })

  it("keeps positional identity separate from duplicate display labels", () => {
    const wrapper = mountGrid()

    expect(wrapper.findAll('button[aria-label="Select column value"]')).toHaveLength(2)
    expect(wrapper.get('[data-testid="grid-cell-row-a-0"]').text()).toBe("left")
    expect(wrapper.get('[data-testid="grid-cell-row-a-1"]').text()).toBe("right")
  })

  it("owns selection while giving controller commands the selected rows and paste request", async () => {
    const wrapper = mount(TabularGrid, {
      props: {
        columns: COLUMNS,
        rows: [{ id: "row-a", values: ["left", "right"] }],
        page: 0,
        pageSize: 100,
        filters: [],
        sort: [],
        layout: defaultColumnLayout(COLUMNS),
      },
      slots: {
        // The writing group, because a paste is a write: what the row offers
        // is handed out a group at a time now.
        "commands-write": ({ selectedRowIndexes, requestPaste }) =>
          h(
            "button",
            {
              "data-testid": "controller-command",
              onClick: requestPaste,
            },
            selectedRowIndexes.join(",")
          ),
      },
      global: { plugins: [Quasar] },
    })

    await wrapper.get('[data-testid="grid-select-row-row-a"]').trigger("click")
    expect(wrapper.get('[data-testid="controller-command"]').text()).toBe("0")

    await wrapper.get('[data-testid="controller-command"]').trigger("click")
    expect(first(wrapper.emitted("paste") ?? [])[0]).toMatchObject({
      columns: [
        { id: "0", valueIndex: 0 },
        { id: "1", valueIndex: 1 },
      ],
    })
  })

  it("pastes what the browser's paste event carries, without reading the clipboard", async () => {
    const wrapper = mountGrid()
    await wrapper.get('[data-testid="grid-select-row-row-a"]').trigger("click")

    const event = new Event("paste", { bubbles: true, cancelable: true })
    Object.defineProperty(event, "clipboardData", {
      value: { getData: (type: string) => (type === "text/plain" ? "x\ty" : "") },
    })
    wrapper.get('[data-testid="grid-focus"]').element.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
    expect(first(wrapper.emitted("paste") ?? [])[0]).toMatchObject({ text: "x\ty" })
    expect(navigator.clipboard.readText).not.toHaveBeenCalled()
  })

  it("adds and removes whole rows with Ctrl+click on their selectors", async () => {
    const wrapper = mount(TabularGrid, {
      props: {
        columns: COLUMNS,
        rows: [
          { id: "row-a", values: ["a1", "a2"] },
          { id: "row-b", values: ["b1", "b2"] },
          { id: "row-c", values: ["c1", "c2"] },
        ],
        page: 0,
        pageSize: 100,
        filters: [],
        sort: [],
        layout: defaultColumnLayout(COLUMNS),
      },
      slots: {
        "commands-write": ({ selectedRowIndexes }) =>
          h("button", { "data-testid": "controller-command" }, selectedRowIndexes.join(",")),
      },
      global: { plugins: [Quasar] },
    })

    await wrapper.get('[data-testid="grid-select-row-row-a"]').trigger("click")
    expect(wrapper.get('[data-testid="controller-command"]').text()).toBe("0")

    await wrapper.get('[data-testid="grid-select-row-row-c"]').trigger("click", { ctrlKey: true })
    expect(wrapper.get('[data-testid="controller-command"]').text()).toBe("0,2")

    await wrapper.get('[data-testid="grid-select-row-row-a"]').trigger("click", { ctrlKey: true })
    expect(wrapper.get('[data-testid="controller-command"]').text()).toBe("2")
  })

  it("extends whole rows from the anchor with Shift+click on their selectors", async () => {
    const wrapper = mount(TabularGrid, {
      props: {
        columns: COLUMNS,
        rows: [
          { id: "row-a", values: ["a1", "a2"] },
          { id: "row-b", values: ["b1", "b2"] },
          { id: "row-c", values: ["c1", "c2"] },
        ],
        page: 0,
        pageSize: 100,
        filters: [],
        sort: [],
        layout: defaultColumnLayout(COLUMNS),
      },
      slots: {
        "commands-write": ({ selectedRowIndexes }) =>
          h("button", { "data-testid": "controller-command" }, selectedRowIndexes.join(",")),
      },
      global: { plugins: [Quasar] },
    })

    await wrapper.get('[data-testid="grid-select-row-row-a"]').trigger("click")
    await wrapper.get('[data-testid="grid-select-row-row-c"]').trigger("click", { shiftKey: true })
    expect(wrapper.get('[data-testid="controller-command"]').text()).toBe("0,1,2")

    // A cell pressed since replaces the selection, and the anchor with it.
    await wrapper.get('[data-testid="grid-cell-row-c-0"]').trigger("mousedown")
    await wrapper.get('[data-testid="grid-select-row-row-b"]').trigger("click", { shiftKey: true })
    expect(wrapper.get('[data-testid="controller-command"]').text()).toBe("1")
  })

  it("emits controlled sort, layout and paging changes", async () => {
    const wrapper = mountGrid({ hasMore: true })

    await wrapper.get('[data-testid="grid-sort-direction-0"]').trigger("click")
    expect(first(wrapper.emitted("update:sort") ?? [])[0]).toEqual([
      { column: "0", descending: false },
    ])

    await wrapper.get('[data-testid="grid-hide-1"]').trigger("click")
    expect(first(wrapper.emitted("update:layout") ?? [])[0]).toMatchObject({
      columnVisibility: { 1: false },
    })

    await wrapper.get('[data-testid="grid-next"]').trigger("click")
    expect(first(wrapper.emitted("turn-page") ?? [])[0]).toBe(1)
  })

  it("presents loading and error states without a controller-specific branch", async () => {
    const wrapper = mountGrid({ loading: true, rows: [] })
    expect(wrapper.find('[data-testid="grid-skeleton"]').exists()).toBe(true)

    await wrapper.setProps({ loading: false, error: "Source unavailable" })
    expect(wrapper.get('[data-testid="grid-error"]').text()).toContain("Source unavailable")

    await wrapper.get('[data-testid="grid-retry"]').trigger("click")
    await flushPromises()
    expect(wrapper.emitted("retry")).toHaveLength(1)
  })

  it("hints with the kit tooltip rather than the browser's own", async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(TabularGrid, {
        props: {
          columns: COLUMNS,
          rows: [
            { id: "row-a", values: ["left", "right"] },
            { id: "row-b", values: ["left", "right"] },
          ],
          page: 0,
          pageSize: 100,
          filters: [],
          sort: [],
          layout: defaultColumnLayout(COLUMNS),
          editableRowIds: ["row-a", "row-b"],
        },
        attachTo: document.body,
        global: { plugins: [Quasar] },
      })

      // No native hint anywhere: an ordinary cell draws no tooltip at all.
      const editable = wrapper.get('[data-testid="grid-cell-row-a-0"]')
      expect(editable.attributes("title")).toBeUndefined()
      const plain = wrapper.get('[data-testid="grid-cell-row-a-1"]')
      expect(plain.attributes("title")).toBeUndefined()
      expect(plain.findComponent(AppTooltip).exists()).toBe(false)
      expect(
        wrapper.get('[data-testid="grid-select-row-row-a"]').attributes("title")
      ).toBeUndefined()

      // A tooltip a cell would be thousands on a full page: only the row
      // under the pointer has them.
      expect(wrapper.get("tbody").findAllComponents(AppTooltip)).toHaveLength(0)
      await wrapper.get('[data-testid="grid-row-row-a"]').trigger("mouseenter")
      expect(wrapper.get('[data-testid="grid-row-row-a"]').findAllComponents(AppTooltip)).toHaveLength(2)
      expect(wrapper.get('[data-testid="grid-row-row-b"]').findAllComponents(AppTooltip)).toHaveLength(0)

      editable.element.dispatchEvent(new MouseEvent("mouseenter"))
      await vi.advanceTimersByTimeAsync(500)
      await flushPromises()
      expect(document.body.querySelector(".q-tooltip")?.textContent).toBe(
        "Double-click to edit"
      )
      wrapper.unmount()
    } finally {
      document.body.innerHTML = ""
      vi.useRealTimers()
    }
  })

  it("leaves a mark in the cell its own tooltip", async () => {
    const wrapper = mount(TabularGrid, {
      props: {
        columns: COLUMNS,
        rows: [{ id: "row-a", values: ["left", "right"] }],
        page: 0,
        pageSize: 100,
        filters: [],
        sort: [],
        layout: defaultColumnLayout(COLUMNS),
        editableRowIds: ["row-a"],
      },
      slots: {
        "cell-overlay": () => h("button", { "data-testid": "mark" }),
      },
      global: { plugins: [Quasar] },
    })
    const cell = wrapper.get('[data-testid="grid-cell-row-a-0"]')
    await wrapper.get('[data-testid="grid-row-row-a"]').trigger("mouseenter")
    await cell.trigger("mouseover")
    expect(cell.findComponent(AppTooltip).exists()).toBe(true)

    await cell.get('[data-testid="mark"]').trigger("mouseover")
    expect(cell.findComponent(AppTooltip).exists()).toBe(false)

    await cell.get(".data-grid__value").trigger("mouseover")
    expect(cell.findComponent(AppTooltip).exists()).toBe(true)
  })
})
