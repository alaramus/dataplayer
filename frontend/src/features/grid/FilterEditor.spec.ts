import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"
import { AppInput } from "@/shared/ui"
import { at, first } from "@/shared/testing/collections"

import FilterEditor from "./FilterEditor.vue"
import GridHeader from "./GridHeader.vue"
import { defaultColumnLayout } from "./columnLayout"
import type { Filter } from "./types"

const STATUS_COLUMN: FetchColumn = {
  name: "status",
  type: { sql: "project_status", category: "enum", enum_values: ["active", "paused"] },
  sortable: true,
  filter_operators: ["eq", "in", "is_null"],
}
const NAME_COLUMN: FetchColumn = {
  name: "name",
  type: { sql: "text", category: "string" },
  sortable: true,
  filter_operators: ["eq", "contains", "is_null"],
}
const FILE_COLUMN: FetchColumn = {
  name: "line",
  type: { sql: "text", category: "string" },
  sortable: false,
  filter_operators: [],
}

function mountHeader(columns: FetchColumn[], filters: Filter[] = []) {
  return mount(GridHeader, {
    props: {
      pageSize: 100,
      columns,
      filters,
      sort: [],
      layout: defaultColumnLayout(columns),
      selectedColumn: null,
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

    value.vm.$emit("keyup", new KeyboardEvent("keyup", { key: "Enter" }))
    await wrapper.vm.$nextTick()

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

  it("disables filtering with the source explanation when no operator exists", () => {
    const wrapper = mountHeader([FILE_COLUMN])
    const command = wrapper.get('[data-testid="grid-filter-command"]')

    expect(command.attributes("title")).toBe("This source does not support filtering")
    expect(command.get('[data-testid="grid-filter"]').attributes("disabled")).toBeDefined()
  })
})
