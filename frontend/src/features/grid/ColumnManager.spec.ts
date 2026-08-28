import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"
import { AppCheckbox } from "@/shared/ui"
import { at, first } from "@/shared/testing/collections"

import ColumnManager from "./ColumnManager.vue"
import GridHeader from "./GridHeader.vue"
import { defaultColumnLayout } from "./columnLayout"
import type { ColumnLayoutState } from "./columnLayout"

const COLUMNS: FetchColumn[] = [
  { name: "id", type: { sql: "bigint", category: "number" }, sortable: true },
  { name: "name", type: { sql: "text", category: "string" }, sortable: true },
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

  it("keeps the current-column pin command disabled until a column is selected", () => {
    const wrapper = mount(GridHeader, {
      props: {
        pageSize: 100,
        columns: COLUMNS,
        filters: [],
        sort: [],
        layout: defaultColumnLayout(COLUMNS),
        selectedColumn: null,
      },
      global: { plugins: [Quasar] },
    })

    expect(wrapper.get('[data-testid="grid-pin-current"]').attributes("disabled")).toBeDefined()
  })

  it("uses one component tooltip for disabled commands, without a native duplicate", () => {
    const wrapper = mount(GridHeader, {
      props: {
        pageSize: 100,
        columns: [],
        filters: [],
        sort: [],
        layout: defaultColumnLayout([]),
        selectedColumn: null,
        canInsert: false,
        insertReason: "Insert unavailable",
        canDelete: false,
        deleteReason: "Delete unavailable",
      },
      global: { plugins: [Quasar] },
    })

    for (const testId of [
      "grid-filter-command",
      "grid-sort-command",
      "grid-insert-command",
      "grid-delete-command",
    ]) {
      expect(wrapper.get(`[data-testid="${testId}"]`).attributes("title")).toBeUndefined()
    }
  })
})
