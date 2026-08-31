import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"

import SqlPanel from "./SqlPanel.vue"

const openRows = vi.fn()
let registry = createReloadRegistry()

const CodeEditorStub = {
  props: {
    modelValue: { type: String, required: true },
    filename: { type: String, required: true },
    readonly: { type: Boolean, default: false },
  },
  template: `<textarea :value="modelValue" :readonly="readonly" :aria-label="filename" />`,
}

const Host = defineComponent({
  components: { SqlPanel },
  setup() {
    provideReloadRegistry(registry)
  },
  template: `
    <SqlPanel
      panel-id="content:c1:public.orders:sql"
      connector-id="c1"
      node-id="public.orders"
      title="orders"
      connector-name="local pg"
      adapter-type="postgres"
      table-title="View as table"
    />
  `,
})

function mountPanel() {
  return mount(Host, {
    global: {
      plugins: [
        Quasar,
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { retry: false, gcTime: 0 } },
            }),
          },
        ],
      ],
      provide: {
        [workspaceActionsKey as symbol]: { openRows },
      },
      stubs: { CodeEditor: CodeEditorStub },
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  openRows.mockReset()
  registry = createReloadRegistry()
})

describe("the source-issued SQL panel", () => {
  it("reads bounded content and never asks for an editable document", async () => {
    const read = vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: {
        kind: "sql",
        text: 'CREATE TABLE "public"."orders" ();\n',
        truncated: false,
        notice: null,
      },
    } as never)
    const editor = vi.spyOn(ConnectorsService, "readEditorContent")

    const wrapper = mountPanel()
    await flushPromises()

    expect(read).toHaveBeenCalledWith(
      expect.objectContaining({
        body: { node_id: "public.orders", representation: "sql" },
      })
    )
    expect(editor).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="sql-editor"]').attributes("readonly")).toBeDefined()
    expect(wrapper.get('[data-testid="sql-editor"]').element).toHaveProperty(
      "value",
      'CREATE TABLE "public"."orders" ();\n'
    )
  })

  it("re-reads through the panel reload command", async () => {
    const read = vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: { kind: "sql", text: "CREATE TABLE one ();", truncated: false, notice: null },
    } as never)

    mountPanel()
    await flushPromises()
    expect(await registry.reload("content:c1:public.orders:sql")).toBe(true)
    await flushPromises()

    expect(read).toHaveBeenCalledTimes(2)
  })

  it("returns to the preferred table representation", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: { kind: "sql", text: "CREATE TABLE one ();", truncated: false, notice: null },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="sql-view-table"]').trigger("click")

    expect(openRows).toHaveBeenCalledWith(
      expect.objectContaining({ nodeId: "public.orders", title: "orders" })
    )
  })
})
