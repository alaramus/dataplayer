import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { Dialog, Notify, Quasar } from "quasar"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService, QueriesService } from "@/client"
import type { QueryDocumentPublic } from "@/client"
import { workspaceActionsKey } from "@/features/workspace/state"
import { withWindowHost } from "@/shared/testing/windows"

import QueryDocumentPanel from "./QueryDocumentPanel.vue"
import { readShadow } from "./draft"

const workspace = {
  openQueryDocument: vi.fn(),
  openQueryDraft: vi.fn(),
  rememberedQuery: vi.fn(),
  renameQueryDocument: vi.fn(),
  closeQueryDocument: vi.fn(),
}

/**
 * The editor is CodeMirror in a browser and a textarea here.
 *
 * What this file is about is the rules around saving: what is sent, what a
 * conflict offers and what a tab keeps when the server cannot be reached.
 */
const CodeEditorStub = defineComponent({
  props: { modelValue: { type: String, required: true } },
  emits: ["update:modelValue"],
  template: `
    <textarea
      data-testid="query-editor"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
    />
  `,
})

function document(overrides: Partial<QueryDocumentPublic> = {}): QueryDocumentPublic {
  return {
    id: "d1",
    connector_id: "c1",
    connector_label: "local pg",
    title: null,
    body: "select 1",
    revision: 3,
    search_path: ["public"],
    layout: { split_ratio: 0.6, wrap: false },
    ...overrides,
  }
}

function conflict(): AxiosError {
  const error = new AxiosError("Conflict")
  error.response = {
    status: 409,
    statusText: "Conflict",
    data: { detail: { message: "This document changed elsewhere", revision: 4 } },
    headers: {},
    config: { headers: {} },
  } as never
  return error
}

function mountPanel(
  props: Record<string, unknown> = { panelId: "query:d1", documentId: "d1" }
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(withWindowHost(QueryDocumentPanel, props), {
    global: {
      plugins: [
        [Quasar, { plugins: { Dialog, Notify } }],
        [VueQueryPlugin, { queryClient }],
        // The console tells the rest of the workspace when it has changed the
        // structure of a source, and that word is kept in a store (D66).
        createPinia(),
      ],
      provide: { [workspaceActionsKey as symbol]: workspace },
      stubs: { CodeEditor: CodeEditorStub },
    },
  })
}

async function type(wrapper: ReturnType<typeof mountPanel>, text: string) {
  await wrapper.get('[data-testid="query-editor"]').setValue(text)
  await flushPromises()
  // Past the pause typing has to stop for before a save is worth a revision.
  await vi.advanceTimersByTimeAsync(900)
  await flushPromises()
}

beforeEach(() => {
  vi.restoreAllMocks()
  // The console asks what its connection is called now rather than trusting
  // the name copied into the tab when it opened (D66). Nothing here is about
  // that, so the list is simply empty and the document's own label stands.
  vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
    data: { data: [], count: 0 },
  } as never)
  vi.useFakeTimers()
  sessionStorage.clear()
  workspace.openQueryDocument.mockReset()
  workspace.renameQueryDocument.mockReset()
  workspace.closeQueryDocument.mockReset()
})

describe("one console", () => {
  it("saves what changed once typing stops, on the revision it started from", async () => {
    vi.spyOn(QueriesService, "readDocument").mockResolvedValue({ data: document() } as never)
    const save = vi
      .spyOn(QueriesService, "updateDocument")
      .mockResolvedValue({ data: document({ body: "select 2", revision: 4 }) } as never)
    const wrapper = mountPanel()
    await flushPromises()

    await type(wrapper, "select 2")

    expect(save).toHaveBeenCalledWith({
      path: { document_id: "d1" },
      body: { revision: 3, body: "select 2" },
    })
    expect(wrapper.get('[data-testid="query-state"]').text()).toBe("Saved")
  })

  it("offers three answers when the document changed elsewhere, and takes the remote text", async () => {
    const read = vi.spyOn(QueriesService, "readDocument")
    read.mockResolvedValueOnce({ data: document() } as never)
    read.mockResolvedValue({ data: document({ body: "theirs", revision: 4 }) } as never)
    vi.spyOn(QueriesService, "updateDocument").mockRejectedValue(conflict())
    const wrapper = mountPanel()
    await flushPromises()

    await type(wrapper, "mine")

    expect(wrapper.find('[data-testid="query-conflict"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="query-state"]').text()).toBe("Changed elsewhere")

    await wrapper.get('[data-testid="conflict-use-remote"]').trigger("click")
    await flushPromises()

    expect(
      (wrapper.get('[data-testid="query-editor"]').element as HTMLTextAreaElement).value
    ).toBe("theirs")
    expect(wrapper.find('[data-testid="query-conflict"]').exists()).toBe(false)
  })

  it("writes your own text over the revision that is there now when you keep it", async () => {
    const read = vi.spyOn(QueriesService, "readDocument")
    read.mockResolvedValueOnce({ data: document() } as never)
    read.mockResolvedValue({ data: document({ body: "theirs", revision: 4 }) } as never)
    const save = vi.spyOn(QueriesService, "updateDocument")
    save.mockRejectedValueOnce(conflict())
    save.mockResolvedValue({ data: document({ body: "mine", revision: 5 }) } as never)
    const wrapper = mountPanel()
    await flushPromises()
    await type(wrapper, "mine")

    await wrapper.get('[data-testid="conflict-keep-mine"]').trigger("click")
    await flushPromises()

    expect(save).toHaveBeenLastCalledWith({
      path: { document_id: "d1" },
      body: {
        revision: 4,
        body: "mine",
        title: null,
        layout: { split_ratio: 0.6, wrap: false },
      },
    })
    expect(wrapper.get('[data-testid="query-state"]').text()).toBe("Saved")
  })

  it("keeps unsaved text in this tab when the server cannot be reached", async () => {
    vi.spyOn(QueriesService, "readDocument").mockResolvedValue({ data: document() } as never)
    vi.spyOn(QueriesService, "updateDocument").mockRejectedValue(new Error("Network Error"))
    const wrapper = mountPanel()
    await flushPromises()

    await type(wrapper, "select 2")

    expect(wrapper.find('[data-testid="query-unsynchronised"]').exists()).toBe(true)
    expect(readShadow("d1")).toMatchObject({ revision: 3, body: "select 2" })
  })

  it("offers the text of an interrupted session back after a reload", async () => {
    sessionStorage.setItem(
      "dp.query.shadow.d1",
      JSON.stringify({ documentId: "d1", revision: 3, body: "unsaved", title: null })
    )
    vi.spyOn(QueriesService, "readDocument").mockResolvedValue({ data: document() } as never)
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-testid="query-shadow"]').exists()).toBe(true)
    await wrapper.get('[data-testid="shadow-restore"]').trigger("click")
    await flushPromises()

    expect(
      (wrapper.get('[data-testid="query-editor"]').element as HTMLTextAreaElement).value
    ).toBe("unsaved")
  })

  it("keeps a console out of the library until somebody asks for it", async () => {
    // Opening one used to put an "Untitled" into the library before a word had
    // been typed, and every table opened as a query left another behind (D65).
    sessionStorage.setItem(
      "dp.query.draft.n1",
      JSON.stringify({ body: "select 7", title: null, wrap: false, split: 0.6 })
    )
    const reading = vi.spyOn(QueriesService, "readDocument")
    const creating = vi.spyOn(QueriesService, "createDocument")
    const wrapper = mountPanel({
      panelId: "query:draft:n1",
      draftId: "n1",
      connectorId: "c1",
      connectorName: "local pg",
    })
    await flushPromises()

    expect(reading).not.toHaveBeenCalled()
    expect(creating).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="query-state"]').text()).toBe("Not kept")
    expect(
      (wrapper.get('[data-testid="query-editor"]').element as HTMLTextAreaElement).value
    ).toBe("select 7")

    // Typing writes to this tab and to nothing else.
    await type(wrapper, "select 8")
    expect(creating).not.toHaveBeenCalled()
    expect(JSON.parse(sessionStorage.getItem("dp.query.draft.n1") ?? "{}").body).toBe(
      "select 8"
    )
  })

  it("puts the console into the library when Remember is pressed", async () => {
    sessionStorage.setItem(
      "dp.query.draft.n1",
      JSON.stringify({ body: "select 7", title: "Kept", wrap: false, split: 0.6 })
    )
    const creating = vi
      .spyOn(QueriesService, "createDocument")
      .mockResolvedValue({ data: document({ id: "d9", title: "Kept" }) } as never)
    const wrapper = mountPanel({
      panelId: "query:draft:n1",
      draftId: "n1",
      connectorId: "c1",
      connectorName: "local pg",
    })
    await flushPromises()

    await wrapper.get('[data-testid="query-remember"]').trigger("click")
    await flushPromises()

    expect(creating).toHaveBeenCalledWith({
      body: { connector_id: "c1", title: "Kept", body: "select 7" },
    })
    // The same tab, now about a document, and the text it was holding is no
    // longer needed anywhere but the server.
    expect(workspace.rememberedQuery).toHaveBeenCalledWith(
      "query:draft:n1",
      expect.objectContaining({ documentId: "d9", title: "Kept" })
    )
    expect(sessionStorage.getItem("dp.query.draft.n1")).toBeNull()
  })

  it("says so when the connection this query was written against has gone", async () => {
    vi.spyOn(QueriesService, "readDocument").mockResolvedValue({
      data: document({ connector_id: null, connector_label: null }),
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="query-context"]').text()).toContain(
      "Connection unavailable"
    )
  })
})
