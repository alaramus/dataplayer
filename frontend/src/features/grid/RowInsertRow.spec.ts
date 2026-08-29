import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"

import RowInsertRow from "./RowInsertRow.vue"
import type { InsertGridColumn } from "./RowInsertRow.vue"

function offered(column: FetchColumn): InsertGridColumn {
  return { column, pinned: false, style: {} }
}

const id: FetchColumn = {
  name: "id",
  type: { sql: "integer", category: "number" },
  insertable: true,
  has_default: true,
}
const name: FetchColumn = {
  name: "name",
  type: { sql: "text", category: "string" },
  insertable: true,
}
const active: FetchColumn = {
  name: "active",
  type: { sql: "boolean", category: "boolean" },
  insertable: true,
  insert_required: true,
}

function mountRow(columns: FetchColumn[]) {
  return mount(RowInsertRow, {
    props: { columns: columns.map(offered), rowNumber: 1, saving: false },
    global: { plugins: [Quasar] },
  })
}

describe("the row a new record is typed into", () => {
  it("starts a column revealed later from that column's own rules", async () => {
    // The grid can show, hide or pin a column while this row is open, so the
    // columns it was created with are not the columns it will be saved with.
    const wrapper = mountRow([id])

    await wrapper.setProps({ columns: [id, active].map(offered) })
    await wrapper.get('[data-testid="grid-insert-save"]').trigger("click")

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual([
      { column: "active", value: "false" },
    ])
    wrapper.unmount()
  })

  it("still sends a value whose column has since left the view", async () => {
    const wrapper = mountRow([id, name])

    await wrapper.get('[data-testid="grid-insert-value-name"]').setValue("Ada")
    await wrapper.setProps({ columns: [id].map(offered) })
    await wrapper.get('[data-testid="grid-insert-save"]').trigger("click")

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual([{ column: "name", value: "Ada" }])
    wrapper.unmount()
  })
})
