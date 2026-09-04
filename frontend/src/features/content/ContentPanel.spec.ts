import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { AxiosError } from "axios"
import { Notify, Quasar } from "quasar"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"
import { createCloseRegistry, provideCloseRegistry } from "@/features/workspace/closable"
import { withWindowHost } from "@/shared/testing/windows"

import ContentPanel from "./ContentPanel.vue"

const openRows = vi.fn()
let registry = createReloadRegistry()
let closings = createCloseRegistry()

// A plain options object rather than defineComponent: two defineComponent
// calls in one file trip vue/one-component-per-file, and only the mounted
// host needs its props typed.
const CodeEditorStub = {
  props: {
    modelValue: { type: String, required: true },
    filename: { type: String, required: true },
    readonly: { type: Boolean, default: false },
  },
  emits: ["update:modelValue"],
  template: `
    <textarea
      :value="modelValue"
      :readonly="readonly"
      :aria-label="filename + ' source'"
      @input="$emit('update:modelValue', $event.target.value)"
    />
  `,
}

const panelId = "content:c1:worker.py:text"

const Host = defineComponent({
  components: { ContentPanel },
  props: { panel: { type: Object, required: true } },
  setup() {
    provideReloadRegistry(registry)
    provideCloseRegistry(closings)
  },
  template: `<ContentPanel v-bind="panel" />`,
})

function mountPanel(overrides: Record<string, unknown> = {}) {
  return mount(withWindowHost(Host, {
    panel: {
      panelId,
      connectorId: "c1",
      nodeId: "worker.py",
      title: "worker.py",
      connectorName: "my files",
      adapterType: "file",
      representation: "text",
      ...overrides,
    },
  }), {
    global: {
      plugins: [
        [Quasar, { plugins: { Notify } }],
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

function editorAnswer(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      text: "print('before')\n",
      filename: "worker.py",
      language_hint: null,
      validation: null,
      version: "version-one",
      writable: true,
      truncated: false,
      reason: null,
      ...overrides,
    },
  } as never
}

function failure(status: number, message: string): AxiosError {
  const cause = new AxiosError("request failed")
  cause.response = { status, data: { detail: { message } } } as never
  return cause
}

beforeEach(() => {
  vi.restoreAllMocks()
  openRows.mockReset()
  registry = createReloadRegistry()
  closings = createCloseRegistry()
})

describe("the file content editor", () => {
  it("asks before discarding dirty content when leaving its server", async () => {
    vi.spyOn(ConnectorsService, "readEditorContent").mockResolvedValue(editorAnswer())
    const wrapper = mountPanel()
    await flushPromises()
    expect(await closings.mayClose(panelId)).toBe(true)
    await wrapper.get('[data-testid="content-editor"]').setValue("unsaved work")
    const leaving = closings.mayClose(panelId)
    await flushPromises()
    expect(wrapper.text()).toContain("Discard file changes?")
    await wrapper.get('[data-testid="confirm-cancel"]').trigger("click")
    expect(await leaving).toBe(false)
    expect(wrapper.get('[data-testid="content-editor"]').element).toHaveProperty("value", "unsaved work")
    wrapper.unmount()
  })
  it("opens the source itself, without asking for a separate viewer", async () => {
    const open = vi.spyOn(ConnectorsService, "readEditorContent").mockResolvedValue(editorAnswer())
    const viewer = vi.spyOn(ConnectorsService, "readContent")

    const wrapper = mountPanel()
    await flushPromises()

    expect(open).toHaveBeenCalledTimes(1)
    expect(viewer).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="content-editor"]').element).toHaveProperty(
      "value",
      "print('before')\n"
    )
  })

  it("saves under the version it loaded and edits on from the one it is given", async () => {
    vi.spyOn(ConnectorsService, "readEditorContent").mockResolvedValue(editorAnswer())
    const save = vi
      .spyOn(ConnectorsService, "updateContent")
      .mockResolvedValueOnce({ data: { version: "version-two" } } as never)
      .mockResolvedValueOnce({ data: { version: "version-three" } } as never)

    const wrapper = mountPanel()
    await flushPromises()
    // Nothing has changed yet, so there is nothing to save.
    expect(wrapper.get('[data-testid="content-save"]').attributes("disabled")).toBeDefined()

    await wrapper.get('[data-testid="content-editor"]').setValue("print('after')\n")
    await wrapper.get('[data-testid="content-save"]').trigger("click")
    await flushPromises()

    expect(save).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        body: { node_id: "worker.py", text: "print('after')\n", version: "version-one" },
      })
    )
    expect(wrapper.find('[data-testid="content-dirty"]').exists()).toBe(false)

    await wrapper.get('[data-testid="content-editor"]').setValue("print('again')\n")
    await wrapper.get('[data-testid="content-save"]').trigger("click")
    await flushPromises()

    expect(save).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        body: { node_id: "worker.py", text: "print('again')\n", version: "version-two" },
      })
    )
  })

  it("keeps the draft and offers a reload when the file moved on underneath", async () => {
    vi.spyOn(ConnectorsService, "readEditorContent").mockResolvedValue(editorAnswer())
    vi.spyOn(ConnectorsService, "updateContent").mockRejectedValue(
      failure(409, "The file changed or was deleted; reload it and try again")
    )

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="content-editor"]').setValue("print('mine')\n")
    await wrapper.get('[data-testid="content-save"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-testid="content-save-error"]').text()).toContain("reload it")
    expect(wrapper.find('[data-testid="content-reload"]').exists()).toBe(true)
    // The edit is still on screen: the failure took nothing away.
    expect(wrapper.get('[data-testid="content-editor"]').element).toHaveProperty(
      "value",
      "print('mine')\n"
    )
  })

  it("says why a file cannot be written and offers no save at all", async () => {
    vi.spyOn(ConnectorsService, "readEditorContent").mockResolvedValue(
      editorAnswer({
        writable: false,
        version: null,
        truncated: true,
        reason: "Files larger than 4 MB are shown as a preview and cannot be edited here.",
      })
    )

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="content-notice"]').text()).toContain("cannot be edited")
    expect(wrapper.find('[data-testid="content-save"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="content-editor"]').attributes("readonly")).toBeDefined()
  })

  it("offers the table only for a node whose source says it has one", async () => {
    vi.spyOn(ConnectorsService, "readEditorContent").mockResolvedValue(editorAnswer())

    const text = mountPanel()
    await flushPromises()
    expect(text.find('[data-testid="content-view-table"]').exists()).toBe(false)

    const json = mountPanel({
      nodeId: "people.json",
      title: "people.json",
      representation: "json",
      tableTitle: "View as table",
    })
    await flushPromises()
    await json.get('[data-testid="content-view-table"]').trigger("click")

    expect(openRows).toHaveBeenCalledWith(expect.objectContaining({ nodeId: "people.json" }))
  })

  it("refuses to re-read a file that has unsaved changes", async () => {
    const open = vi.spyOn(ConnectorsService, "readEditorContent").mockResolvedValue(editorAnswer())

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="content-editor"]').setValue("print('mine')\n")

    expect(await registry.reload(panelId)).toBe(true)
    await flushPromises()

    expect(open).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="content-editor"]').element).toHaveProperty(
      "value",
      "print('mine')\n"
    )
  })
})
