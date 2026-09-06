import { flushPromises, mount } from "@vue/test-utils"
import { h } from "vue"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { first } from "@/shared/testing/collections"

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
})
