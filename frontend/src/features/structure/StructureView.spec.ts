import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { RelationModel } from "@/client"
import { AppInput, AppSelect } from "@/shared/ui"
import { withWindowHost } from "@/shared/testing/windows"

import StructureView from "./StructureView.vue"

const MODEL: RelationModel = {
  node_id: "public.projects",
  schema_name: "public",
  name: "projects",
  kind: "table",
  owner: "postgres",
  persistence: "permanent",
  columns: [
    {
      position: 1,
      name: "name",
      type: { sql: "text", category: "string" },
      nullable: false,
      storage: "extended",
    },
    {
      position: 2,
      name: "note",
      type: { sql: "text", category: "string" },
      nullable: true,
      storage: "extended",
    },
  ],
  constraints: [],
  indexes: [],
  column_changes_supported: true,
  column_type_options: [
    { code: "text", title: "Text", sql: "text" },
    { code: "integer", title: "Integer", sql: "integer" },
  ],
}

function mountView() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(withWindowHost(StructureView, { connectorId: "connector-1", nodeId: "public.projects" }), {
    global: {
      plugins: [[Quasar, { plugins: { Dialog, Notify } }], [VueQueryPlugin, { queryClient }]],
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
  vi.spyOn(ConnectorsService, "readRelationModel").mockResolvedValue({ data: MODEL } as never)
})

describe("relation column changes", () => {
  it("adds a column using a source-owned type code", async () => {
    const add = vi.spyOn(ConnectorsService, "addColumn").mockResolvedValue({
      data: { name: "review_note" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-add-column"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "review_note")
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", "text")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-add-save"]')?.click()
    await flushPromises()

    expect(add).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        name: "review_note",
        type_code: "text",
        nullable: true,
      },
    })
    wrapper.unmount()
  })

  it("drops the exact column only after confirmation", async () => {
    const drop = vi.spyOn(ConnectorsService, "dropColumn").mockResolvedValue({
      data: { name: "name" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-drop-name"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-accept"]')?.click()
    await flushPromises()

    expect(drop).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "name" },
    })
    wrapper.unmount()
  })

  it("renames the exact column without a destructive confirmation", async () => {
    const rename = vi.spyOn(ConnectorsService, "renameColumn").mockResolvedValue({
      data: { name: "display_name" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-rename-name"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "display_name")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-rename-save"]')?.click()
    await flushPromises()

    expect(rename).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "name", new_name: "display_name" },
    })
    wrapper.unmount()
  })

  it("offers the one nullability change the column does not already have", async () => {
    const change = vi.spyOn(ConnectorsService, "changeColumnNullability").mockResolvedValue({
      data: { kind: "changed", name: "name", nullable: true },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-nullability-name"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-nullability-save"]')?.click()
    await flushPromises()

    expect(change).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "name", nullable: true },
    })
    wrapper.unmount()
  })

  it("reads the count of rows in the way instead of treating it as a failure", async () => {
    vi.spyOn(ConnectorsService, "changeColumnNullability").mockResolvedValue({
      data: { kind: "blocked", name: "note", rows_without_value: 4, exact: true },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-nullability-note"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-nullability-save"]')?.click()
    await flushPromises()

    const blocked = document.body.querySelector('[data-testid="structure-nullability-blocked"]')
    expect(blocked?.textContent).toContain("4 rows have no value in note")
    // The dialog stays open, and nothing was reported as an error.
    expect(
      document.body.querySelector('[data-testid="structure-nullability-error"]')
    ).toBeNull()
    wrapper.unmount()
  })

  it("changes a type using a source-owned code and never a cast", async () => {
    const change = vi.spyOn(ConnectorsService, "changeColumnType").mockResolvedValue({
      data: { kind: "changed", name: "note", type_sql: "integer" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-type-note"]').trigger("click")
    await flushPromises()
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", "integer")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-type-save"]')?.click()
    await flushPromises()

    // The opaque code from the source's own list, and nothing resembling a cast.
    expect(change).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", name: "note", type_code: "integer" },
    })
    wrapper.unmount()
  })

  it("reads the count of values the new type cannot take", async () => {
    vi.spyOn(ConnectorsService, "changeColumnType").mockResolvedValue({
      data: { kind: "blocked", name: "note", rows_not_convertible: 7, exact: false },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-type-note"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="structure-type-save"]')?.click()
    await flushPromises()

    const blocked = document.body.querySelector('[data-testid="structure-type-blocked"]')
    expect(blocked?.textContent).toContain("More than 7 rows hold a value")
    expect(document.body.querySelector('[data-testid="structure-type-error"]')).toBeNull()
    wrapper.unmount()
  })

  it("sets an exact literal column default", async () => {
    const changeDefault = vi.spyOn(ConnectorsService, "changeColumnDefault").mockResolvedValue({
      data: { name: "name" },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="structure-default-name"]').trigger("click")
    await flushPromises()
    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="structure-default-value"]'
    )
    if (input === null) throw new Error("default input did not open")
    input.value = "Robert'); DROP TABLE projects; --"
    input.dispatchEvent(new Event("input", { bubbles: true }))
    document.body.querySelector<HTMLElement>('[data-testid="structure-default-save"]')?.click()
    await flushPromises()

    expect(changeDefault).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        name: "name",
        action: "set",
        value: "Robert'); DROP TABLE projects; --",
      },
    })
    wrapper.unmount()
  })
})
