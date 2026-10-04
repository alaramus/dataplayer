import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it } from "vitest"

import { AppInput } from "@/shared/ui"
import { at, first } from "@/shared/testing/collections"

import FilterEditor from "./FilterEditor.vue"
import AppIconButton from "@/shared/ui/AppIconButton.vue"
import GridHeader from "./GridHeader.vue"
import { defaultColumnLayout } from "./columnLayout"
import type { Filter } from "./types"
import type { TabularColumn } from "./tabular"

const STATUS_COLUMN: TabularColumn = {
  id: "status",
  label: "status",
  type: { sql: "project_status", category: "enum", enum_values: ["active", "paused"] },
  sortable: true,
  filter_operators: ["eq", "in", "is_null"],
}
const NAME_COLUMN: TabularColumn = {
  id: "name",
  label: "name",
  type: { sql: "text", category: "string" },
  sortable: true,
  filter_operators: ["eq", "contains", "is_null"],
}
const FILE_COLUMN: TabularColumn = {
  id: "line",
  label: "line",
  type: { sql: "text", category: "string" },
  sortable: false,
  filter_operators: [],
}

/** What the icon button with this icon promises to say on hover. */
function tooltipOf(wrapper: ReturnType<typeof mount>, icon: string): string {
  const button = wrapper
    .findAllComponents(AppIconButton)
    .find((one) => one.props("icon") === icon)
  return String(button?.props("tooltip") ?? "")
}

function mountHeader(columns: TabularColumn[], filters: Filter[] = []) {
  return mount(GridHeader, {
    props: {
      columns,
      filters,
      sort: [],
      layout: defaultColumnLayout(columns),
    },
    global: { plugins: [Quasar] },
  })
}

function mountEditor(filters: Filter[] = []) {
  return mount(FilterEditor, {
    props: { columns: [STATUS_COLUMN, NAME_COLUMN], filters },
    global: { plugins: [Quasar] },
  })
}

beforeEach(() => localStorage.clear())

describe("the filter band", () => {
  it("opens from the stable header", async () => {
    const wrapper = mountHeader([STATUS_COLUMN])

    await wrapper.get('[data-testid="grid-filter"]').trigger("click")

    expect(wrapper.get('[data-testid="grid-filter-editor"]').isVisible()).toBe(true)
  })

  it("applies one complete condition", async () => {
    const wrapper = mountHeader([NAME_COLUMN])
    await wrapper.get('[data-testid="grid-filter"]').trigger("click")
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "core")

    await wrapper.get('[data-testid="grid-filter-apply"]').trigger("click")

    expect(first(wrapper.emitted("update:filters") ?? [])[0]).toEqual([
      { column: "name", op: "eq", value: "core" },
    ])
  })

  it("does not apply an invalid condition", async () => {
    const wrapper = mountHeader([NAME_COLUMN])
    await wrapper.get('[data-testid="grid-filter"]').trigger("click")

    await wrapper.get('[data-testid="grid-filter-apply"]').trigger("click")

    expect(wrapper.emitted("update:filters")).toBeUndefined()
    expect(wrapper.text()).toContain("Enter a value")
  })

  it("applies an in draft with the pending value as a separate item on Enter", async () => {
    const wrapper = mountEditor()
    at(wrapper.findAllComponents({ name: "AppSelect" }), 1).vm.$emit("update:modelValue", "in")
    await wrapper.vm.$nextTick()
    const value = wrapper.findComponent(AppInput)
    value.vm.$emit("update:modelValue", "active")
    await wrapper.vm.$nextTick()

    await value.get("input").trigger("keyup", { key: "Enter" })

    expect(first(wrapper.emitted("apply") ?? [])[0]).toEqual([
      { column: "status", op: "in", values: ["active"] },
    ])
  })

  it("keeps the other conditions when one is deleted", async () => {
    const filters: Filter[] = [
      { column: "status", op: "eq", value: "active" },
      { column: "name", op: "contains", value: "core" },
    ]
    const wrapper = mountEditor(filters)

    await wrapper.get('[data-testid="grid-filter-delete-0"]').trigger("click")

    expect(first(wrapper.emitted("apply") ?? [])[0]).toEqual([filters[1]])
  })

  it("clears every active condition", async () => {
    const wrapper = mountEditor([{ column: "status", op: "is_null" }])

    await wrapper.get('[data-testid="grid-filter-clear"]').trigger("click")

    expect(first(wrapper.emitted("apply") ?? [])[0]).toEqual([])
  })

  it("keeps filtering in its place and says the source will not do it", () => {
    // Greyed rather than gone: a row that changes shape between a table and a
    // file is a row somebody has to read every time, and the sentence is what
    // a button that cannot be pressed is for.
    const wrapper = mountHeader([FILE_COLUMN])

    expect(wrapper.get('[data-testid="grid-filter"]').attributes("disabled")).toBeDefined()
    // The reason is read off the prop rather than the DOM: a tooltip is drawn
    // only once something hovers it, and nothing hovers in jsdom.
    expect(tooltipOf(wrapper, "filter_alt")).toContain("does not filter rows")
  })
})
