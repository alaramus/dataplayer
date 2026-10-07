import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import type { Sort } from "@/client"

import { defaultColumnLayout } from "./columnLayout"
import GridHeader from "./GridHeader.vue"
import type { TabularColumn } from "./tabular"
import type { Filter } from "./types"

const COLUMNS: TabularColumn[] = [
  {
    id: "status",
    label: "status",
    type: { sql: "text", category: "string" },
    sortable: true,
    filter_operators: ["eq"],
  },
]

const FILTERS: Filter[] = [
  { column: "status", op: "eq", value: "active" },
  { column: "status", op: "eq", value: "paused" },
]
const SORT: Sort[] = [{ column: "status" }]

function mountHeader(
  filters: Filter[] = [],
  sort: Sort[] = [],
  layout = defaultColumnLayout(COLUMNS),
) {
  return mount(GridHeader, {
    props: {
      columns: COLUMNS,
      filters,
      sort,
      layout,
    },
    global: { plugins: [Quasar] },
  })
}

describe("the active query indicator", () => {
  it("hides the counts when nothing is applied", () => {
    const wrapper = mountHeader()

    expect(wrapper.find('[data-testid="grid-filter-count"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="grid-sort-count"]').exists()).toBe(false)
  })

  it("wears the filter count without hovering", () => {
    const wrapper = mountHeader(FILTERS)

    expect(wrapper.get('[data-testid="grid-filter-count"]').text()).toContain("2")
  })

  it("wears the sort count without hovering", () => {
    const wrapper = mountHeader([], SORT)

    expect(wrapper.get('[data-testid="grid-sort-count"]').text()).toContain("1")
  })

  it("hides the columns count when nothing is hidden", () => {
    const wrapper = mountHeader()

    expect(wrapper.find('[data-testid="grid-columns-count"]').exists()).toBe(false)
  })

  it("wears the hidden columns count without hovering", () => {
    const layout = { ...defaultColumnLayout(COLUMNS), columnVisibility: { status: false } }
    const wrapper = mountHeader([], [], layout)

    expect(wrapper.get('[data-testid="grid-columns-count"]').text()).toContain("1")
  })
})
