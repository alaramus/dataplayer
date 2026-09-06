import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import { AppCheckbox } from "@/shared/ui"
import { at, first } from "@/shared/testing/collections"

import ColumnManager from "./ColumnManager.vue"
import GridHeader from "./GridHeader.vue"
import { defaultColumnLayout } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"
import type { TabularColumn } from "./tabular"

const COLUMNS: TabularColumn[] = [
  {
    id: "id",
    label: "id",
    type: { sql: "bigint", category: "number" },
    sortable: true,
    filter_operators: [],
  },
  {
    id: "name",
    label: "name",
    type: { sql: "text", category: "string" },
    sortable: true,
    filter_operators: [],
  },
]

function mountManager() {
  return mount(ColumnManager, {
    props: { columns: COLUMNS, layout: defaultColumnLayout(COLUMNS) },
    global: { plugins: [Quasar] },
  })
}

describe("the column manager", () => {
  it("reorders columns with explicit move commands", async () => {
    const wrapper = mountManager()

    await wrapper.get('[data-testid="grid-column-up-name"]').trigger("click")

    expect(first(wrapper.emitted("update:layout") ?? [])[0]).toMatchObject({
      columnOrder: ["name", "id"],
    })
  })

  it("hides a column without removing it from the order", () => {
    const wrapper = mountManager()

    at(wrapper.findAllComponents(AppCheckbox), 1).vm.$emit("update:modelValue", false)

    expect(first(wrapper.emitted("update:layout") ?? [])[0]).toMatchObject({
      columnOrder: ["id", "name"],
      columnVisibility: { name: false },
    })
  })

  it("pins left and unpins the same column", async () => {
    const wrapper = mountManager()

    await wrapper.get('[data-testid="grid-pin-name"]').trigger("click")
    const pinned = first(wrapper.emitted("update:layout") ?? [])[0] as ColumnLayoutState
    expect(pinned).toMatchObject({ pinnedLeft: ["name"] })

    await wrapper.setProps({ layout: pinned })
    await wrapper.get('[data-testid="grid-pin-name"]').trigger("click")
    expect(at(wrapper.emitted("update:layout") ?? [], 1)[0]).toMatchObject({ pinnedLeft: [] })
  })

  it("resets every layout slice", async () => {
    const wrapper = mount(ColumnManager, {
      props: {
        columns: COLUMNS,
        layout: {
          columnOrder: ["name", "id"],
          columnVisibility: { id: false },
          columnSizing: { name: 300 },
          pinnedLeft: ["name"],
        },
      },
      global: { plugins: [Quasar] },
    })

    await wrapper.get('[data-testid="grid-columns-reset"]').trigger("click")

    expect(first(wrapper.emitted("update:layout") ?? [])[0]).toEqual(defaultColumnLayout(COLUMNS))
  })

  it("does not keep a separate pin command in the toolbar", () => {
    const wrapper = mount(GridHeader, {
      props: {
          columns: COLUMNS,
        filters: [],
        sort: [],
        layout: defaultColumnLayout(COLUMNS),
      },
      global: { plugins: [Quasar] },
    })

    expect(wrapper.find('[data-testid="grid-pin-current"]').exists()).toBe(false)
  })

  it("keeps every group and every command, whatever the source can do", () => {
    // The row is the same row on a table, a file and a query result. What a
    // source cannot do is greyed and says so; nothing is dropped, because a
    // command that moves is a command whose place nobody learns.
    const wrapper = mount(GridHeader, {
      props: {
        columns: [],
        filters: [],
        sort: [],
        layout: defaultColumnLayout([]),
      },
      global: { plugins: [Quasar] },
    })

    for (const group of ["view", "open", "out", "write", "tab"]) {
      expect(wrapper.find(`[data-testid="grid-group-${group}"]`).exists()).toBe(true)
    }
    for (const command of ["grid-filter", "grid-sort", "grid-columns", "grid-copy"]) {
      expect(wrapper.get(`[data-testid="${command}"]`).attributes("disabled")).toBeDefined()
    }
  })

  it("names each group over the buttons in it", () => {
    const wrapper = mount(GridHeader, {
      props: { columns: [], filters: [], sort: [], layout: defaultColumnLayout([]) },
      global: { plugins: [Quasar] },
    })

    expect(wrapper.get('[data-testid="grid-group-write"]').text()).toContain(
      "Change the rows"
    )
  })
})
