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
})
