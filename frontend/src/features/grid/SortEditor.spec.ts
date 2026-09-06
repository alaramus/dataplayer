import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import type { Sort } from "@/client"
import { first } from "@/shared/testing/collections"

import AppIconButton from "@/shared/ui/AppIconButton.vue"
import GridHeader from "./GridHeader.vue"
import SortEditor from "./SortEditor.vue"
import { defaultColumnLayout } from "./columnLayout"
import type { TabularColumn } from "./tabular"

const COLUMNS: TabularColumn[] = [
  {
    id: "name",
    label: "name",
    type: { sql: "text", category: "string" },
    sortable: true,
    filter_operators: ["eq"],
  },
  {
    id: "created_at",
    label: "created_at",
    type: { sql: "timestamp", category: "datetime" },
    sortable: true,
    filter_operators: ["eq"],
  },
]

/** What the icon button with this icon promises to say on hover. */
function tooltipOf(wrapper: ReturnType<typeof mount>, icon: string): string {
  const button = wrapper
    .findAllComponents(AppIconButton)
    .find((one) => one.props("icon") === icon)
  return String(button?.props("tooltip") ?? "")
}

function mountHeader(columns: TabularColumn[] = COLUMNS) {
  return mount(GridHeader, {
    props: {
      columns,
      filters: [],
      sort: [],
      layout: defaultColumnLayout(columns),
    },
    global: { plugins: [Quasar] },
  })
}

function mountEditor(sort: Sort[]) {
  return mount(SortEditor, {
    props: { columns: COLUMNS, sort },
    global: { plugins: [Quasar] },
  })
}

describe("the sort editor", () => {
  it("opens from the stable header", async () => {
    const wrapper = mountHeader()

    await wrapper.get('[data-testid="grid-sort"]').trigger("click")

    expect(wrapper.get('[data-testid="grid-sort-editor"]').isVisible()).toBe(true)
  })

  it("reorders the shared ordered state", async () => {
    const sort: Sort[] = [
      { column: "name", descending: true },
      { column: "created_at", descending: false },
    ]
    const wrapper = mountEditor(sort)

    await wrapper.get('[data-testid="grid-sort-up-1"]').trigger("click")

    expect(first(wrapper.emitted("apply") ?? [])[0]).toEqual([sort[1], sort[0]])
  })

  it("removes one key without disturbing the others", async () => {
    const sort: Sort[] = [
      { column: "name", descending: false },
      { column: "created_at", descending: true },
    ]
    const wrapper = mountEditor(sort)

    await wrapper.get('[data-testid="grid-sort-delete-0"]').trigger("click")

    expect(first(wrapper.emitted("apply") ?? [])[0]).toEqual([sort[1]])
  })

  it("clears the ordered state", async () => {
    const wrapper = mountEditor([{ column: "name", descending: false }])

    await wrapper.get('[data-testid="grid-sort-clear"]').trigger("click")

    expect(first(wrapper.emitted("apply") ?? [])[0]).toEqual([])
  })

  it("keeps sorting in its place and says the source will not do it", () => {
    const wrapper = mountHeader(COLUMNS.map((column) => ({ ...column, sortable: false })))

    expect(wrapper.get('[data-testid="grid-sort"]').attributes("disabled")).toBeDefined()
    // The reason is read off the prop rather than the DOM: a tooltip is drawn
    // only once something hovers it, and nothing hovers in jsdom.
    expect(tooltipOf(wrapper, "sort")).toContain("does not sort rows")
  })
})
