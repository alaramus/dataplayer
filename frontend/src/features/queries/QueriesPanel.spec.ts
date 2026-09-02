import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService, QueriesService } from "@/client"
import type { QueryDocumentSummary } from "@/client"
import { ref } from "vue"

import { workspaceActionsKey } from "@/features/workspace/state"
import { withWindowHost } from "@/shared/testing/windows"

import QueriesPanel from "./QueriesPanel.vue"

// The panel takes the connection it was opened from the way every panel takes
// a target: a ref it watches, and one call that spends it.
const queriesTarget = ref<string | null>(null)
const workspace = {
  openQueryDocument: vi.fn(),
  queriesTarget,
  takeQueriesTarget: () => {
    const taken = queriesTarget.value
    queriesTarget.value = null
    return taken
  },
}

function summary(overrides: Partial<QueryDocumentSummary> = {}): QueryDocumentSummary {
  return {
    id: "d1",
    connector_id: "c1",
    connector_label: "local pg",
    title: null,
    preview: "select 1",
    revision: 1,
    ...overrides,
  }
}

function mockConnectors() {
  vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
    data: {
      data: [
        {
          id: "c1",
          name: "local pg",
          adapter_type: "postgres",
          config: {},
          enabled: true,
          access: "own",
        },
      ],
      count: 1,
    },
  } as never)
}

function mountPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(withWindowHost(QueriesPanel, { panelId: "queries" }), {
    global: {
      plugins: [
        [Quasar, { plugins: { Dialog, Notify } }],
        [VueQueryPlugin, { queryClient }],
      ],
      provide: { [workspaceActionsKey as symbol]: workspace },
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  workspace.openQueryDocument.mockReset()
  queriesTarget.value = null
})

describe("the library of queries", () => {
  it("keeps named documents and drafts apart, and shows a draft by its first line", async () => {
    mockConnectors()
    vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: {
        data: [
          summary({ id: "d1", title: "Daily counts", preview: "select count(*)" }),
          summary({ id: "d2", title: null, preview: "select * from invoices" }),
        ],
        count: 2,
      },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.text()).toContain("Named")
    expect(wrapper.text()).toContain("Drafts")
    expect(wrapper.get('[data-testid="query-row-d1"]').text()).toContain("Daily counts")
    const draft = wrapper.get('[data-testid="query-row-d2"]')
    expect(draft.text()).toContain("Untitled query")
    expect(draft.text()).toContain("select * from invoices")
  })

  it("opens the console of the row that was pressed", async () => {
    mockConnectors()
    vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [summary({ id: "d2", title: "Invoices" })], count: 1 },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-query-d2"]').trigger("click")

    expect(workspace.openQueryDocument).toHaveBeenCalledWith({
      documentId: "d2",
      title: "Invoices",
      connectorName: "local pg",
    })
  })

  it("says which connection a query lost rather than leaving the line blank", async () => {
    mockConnectors()
    vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: {
        data: [summary({ connector_id: null, connector_label: null })],
        count: 1,
      },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="query-row-d1"]').text()).toContain(
      "Connection unavailable"
    )
  })

  it("asks the server for what is in Trash rather than filtering the library", async () => {
    mockConnectors()
    const list = vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [], count: 0 },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="queries-trash"]').trigger("click")
    await flushPromises()

    expect(list).toHaveBeenLastCalledWith({
      query: { search: "", trashed: true },
    })
    expect(wrapper.get('[data-testid="queries-empty"]').text()).toContain("Nothing in Trash")
  })

  it("filters itself to the connection it was opened from", async () => {
    // Opened by the command in the bar at the foot of the screen, which
    // belongs to the connection being read (D69). The panel is a singleton,
    // so the connection arrives as a piece of state rather than as a prop.
    mockConnectors()
    const list = vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [], count: 0 },
    } as never)
    queriesTarget.value = "c1"
    mountPanel()
    await flushPromises()

    expect(list).toHaveBeenCalledWith(
      expect.objectContaining({ query: expect.objectContaining({ connector_id: "c1" }) })
    )
  })

  it("cannot open a new query until a connection is chosen", async () => {
    mockConnectors()
    vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [], count: 0 },
    } as never)
    const create = vi.spyOn(QueriesService, "createDocument")
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="new-query"]').trigger("click")
    await flushPromises()

    expect(create).not.toHaveBeenCalled()
  })
})
