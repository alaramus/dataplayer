import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AppTable from "./AppTable.vue"
import type { TableColumns } from "./AppTable.vue"

const COLUMNS: TableColumns = [
  { name: "name", label: "Name", field: "name", align: "left" },
  { name: "kind", label: "Kind", field: "kind", align: "left" },
]

const ROWS = [
  { name: "postgres-local", kind: "postgres" },
  { name: "my files", kind: "file" },
]

function mountTable(props: Record<string, unknown> = {}, slots = {}) {
  return mount(AppTable, {
    global: { plugins: [Quasar] },
    props: { rows: ROWS, columns: COLUMNS, rowKey: "name", ...props },
    slots,
  })
}

describe("AppTable", () => {
  it("renders a row per record", () => {
    expect(mountTable().findAll("tbody tr")).toHaveLength(2)
  })

  it("says what the caller wants said when there is nothing", () => {
    expect(mountTable({ rows: [], emptyText: "No connections yet" }).text()).toContain(
      "No connections yet"
    )
  })

  // The cell slots of a table are named after its columns, so the kit cannot
  // enumerate them. This is the one component that forwards slots by iterating.
  it("forwards a slot named after a column", () => {
    const wrapper = mountTable(
      {},
      { "body-cell-kind": '<td data-testid="kind-cell">badge</td>' }
    )

    expect(wrapper.findAll("[data-testid='kind-cell']")).toHaveLength(2)
  })

  it("forwards the generic body-cell slot", () => {
    const wrapper = mountTable({}, { "body-cell": '<td data-testid="any-cell">x</td>' })

    expect(wrapper.findAll("[data-testid='any-cell']")).toHaveLength(4)
  })

  it("hides the pager when the caller pages against the server", () => {
    expect(mountTable({ paged: false }).find(".q-table__bottom").exists()).toBe(false)
    expect(mountTable({ paged: true }).find(".q-table__bottom").exists()).toBe(true)
  })
})
