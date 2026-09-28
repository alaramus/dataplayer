import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService, QueriesService } from "@/client"
import type { QueryDocumentSummary } from "@/client"

import { workspaceActionsKey } from "@/features/workspace/state"
import { withWindowHost } from "@/shared/testing/windows"
import { AppIconButton } from "@/shared/ui"

import { useQueriesLibrary } from "./library"
import QueriesTool from "./QueriesTool.vue"

const workspace = {
  openQueryDocument: vi.fn(),
}
const library = useQueriesLibrary()

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
  return mount(withWindowHost(QueriesTool, {}), {
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
  // The library shows the runs of its queries; none of these tests is about
  // runs, so there are none rather than a request to the network.
  vi.spyOn(QueriesService, "listRuns").mockResolvedValue({
    data: { data: [], count: 0 },
  } as never)
  workspace.openQueryDocument.mockReset()
  // Module state, kept while the panel is hidden: each test starts afresh.
  library.connectorId.value = null
  library.place.value = "favorites"
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
    // Deleting a document asks first and never comes back, so its button is
    // in the caution colour; the bar's own buttons say something else and are
    // not what this asserts.
    expect(
      wrapper
        .findAllComponents(AppIconButton)
        .filter((button) => button.props("tooltip") === "Delete query")
        .map((button) => button.props("variant"))
    ).toEqual(["danger-quiet", "danger-quiet"])
  })

  it("opens the console of the row that was pressed", async () => {
    mockConnectors()
    vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [summary({ id: "d2", title: "Invoices" })], count: 1 },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="open-query-d2"]').trigger("click")

    // The connection travels with the request: a console restored from a
    // saved document is written against one, and the panel carries its id
    // rather than looking it up again by name.
    expect(workspace.openQueryDocument).toHaveBeenCalledWith({
      documentId: "d2",
      connectorId: "c1",
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

  it("shows saved queries and run history without a Trash place", async () => {
    mockConnectors()
    vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [], count: 0 },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.get('[data-testid="queries-places-history"]').trigger("click")
    await flushPromises()
    expect(wrapper.find('[data-testid="queries-history-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="queries-places-trash"]').exists()).toBe(false)
    await wrapper.get('[data-testid="queries-places-favorites"]').trigger("click")
    await flushPromises()
    expect(wrapper.find('[data-testid="queries-history-list"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="queries-empty"]').text()).toContain("No favorites yet")
  })

  it("deletes a run from history only once that is confirmed", async () => {
    mockConnectors()
    vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [], count: 0 },
    } as never)
    vi.spyOn(QueriesService, "listRuns").mockResolvedValue({
      data: {
        data: [{
          id: "r1",
          connector_id: "c1",
          document_id: null,
          status: "succeeded",
          scope: "read",
          statement_count: 1,
          preview: "select 1",
        }],
        count: 1,
      },
    } as never)
    const removed = vi.spyOn(QueriesService, "deleteRuns").mockResolvedValue({
      data: { message: "Deleted" },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="queries-places-history"]').trigger("click")
    await flushPromises()

    await wrapper.get('[data-testid="history-delete-r1"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-cancel"]')?.click()
    await flushPromises()
    expect(removed).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="history-delete-r1"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-accept"]')?.click()
    await flushPromises()
    expect(removed).toHaveBeenCalledWith({ body: { kind: "selected", ids: ["r1"] } })
    wrapper.unmount()
  })

  it("filters itself to the connection it was opened from", async () => {
    // Aimed by the button on the rail, which belongs to the connection being
    // read (D69); nothing open leaves the filter as it was.
    mockConnectors()
    const list = vi.spyOn(QueriesService, "listDocuments").mockResolvedValue({
      data: { data: [], count: 0 },
    } as never)
    library.aim("c1")
    library.aim(null)
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
