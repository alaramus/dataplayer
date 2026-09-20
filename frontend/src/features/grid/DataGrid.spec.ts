import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { AxiosError } from "axios"
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AdaptersService, ConnectorsService } from "@/client"
import type { FetchColumn, FetchResult } from "@/client"
import { AppSelect } from "@/shared/ui"
import { AppIconButton, AppInput } from "@/shared/ui"
import { createOperations, operationsKey } from "@/shared/operations"
import { withWindowHost } from "@/shared/testing/windows"
import { notices } from "@/shared/notifications"

import CreateTableDialog from "./CreateTableDialog.vue"
import DataGrid from "./DataGrid.vue"
import type { Filter } from "./types"
import { loadGridState, saveGridState } from "./persist"

function result(offset: number, limit: number): FetchResult {
  return {
    columns: [
      {
        name: "id",
        type: { sql: "bigint", category: "number" },
        sortable: true,
        filter_operators: ["eq", "gt", "is_null"],
      },
      {
        name: "name",
        type: { sql: "text", category: "string" },
        sortable: true,
        filter_operators: ["eq", "contains", "is_null"],
      },
    ],
    rows: Array.from({ length: limit }, (_, index) => [
      String(offset + index + 1),
      `Project ${offset + index + 1}`,
    ]),
    has_more: true,
    export_supported: true,
    // What the server sends for an ordinary relation: everything the toolbar
    // has. A report is what withdraws them (D72).
    page_commands: ["download", "chart", "share", "create_relation", "query"],
  }
}

function mockPages() {
  return vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) => {
    const body = options.body
    return Promise.resolve({ data: result(body.offset ?? 0, body.limit ?? 100) }) as never
  })
}

function mountGrid(
  props: {
    title?: string
    canDescribe?: boolean
    canQuery?: boolean
    contentTitle?: string
    referenceFilters?: Filter[] | null
  } = {}
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(
    withWindowHost(DataGrid, {
      connectorId: "connector-1",
      nodeId: "public.projects",
      ...props,
    }),
    {
      global: {
        plugins: [
          [Quasar, { plugins: { Dialog, Notify } }],
          [VueQueryPlugin, { queryClient }],
          // The grid says when a run has changed the structure of a source,
          // and that word is kept in a store (D66): without one the component
          // cannot be mounted at all.
          createPinia(),
        ],
        // What the application provides at its root: an action opened from
        // over the rows reports itself here while it runs (D113).
        provide: { [operationsKey as symbol]: createOperations() },
      },
    }
  )
}

/** One animation frame, which is how often a drag resize is applied. */
function nextFrame(): Promise<void> {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      resolve()
    })
  })
}

beforeEach(() => {
  // jsdom does not let navigator.clipboard be assigned over, and the grid
  // reaches it through the kit's own boundary in both directions.
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: () => Promise.resolve(),
      readText: () => Promise.resolve(""),
    },
  })
  localStorage.clear()
  vi.restoreAllMocks()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
  // Every grid asks what points at its relation (D110). Most of these tests
  // are about something else, and an unmocked call would reach the network.
  vi.spyOn(ConnectorsService, "arrivingReferences").mockResolvedValue({
    data: [],
  } as never)
  // And what the source offers to do to this node from above its rows (D79).
  vi.spyOn(ConnectorsService, "readActions").mockResolvedValue({
    data: [],
  } as never)
  // The new-table window lists where a table can go: the connections and the
  // types they are of. The one test about it names its own.
  vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
    data: { data: [], count: 0 },
  } as never)
  vi.spyOn(AdaptersService, "readAdapterTypes").mockResolvedValue({ data: [] } as never)
})

describe("the basic data grid", () => {
  it("creates a new table from the rows through the chosen destination", async () => {
    mockPages()
    vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
      data: { data: [] },
    } as never)
    const create = vi
      .spyOn(ConnectorsService, "createRelationFromSource")
      .mockResolvedValue({
        data: { node: { name: "project_copy" }, inserted: 100 },
      } as never)
    const wrapper = mountGrid({ title: "projects.csv" })
    await flushPromises()

    await wrapper.get('[data-testid="grid-create-table"]').trigger("click")
    const dialog = wrapper.findComponent(CreateTableDialog)
    dialog.vm.$emit("run", {
      connectorId: "target-1",
      parentNodeId: "public",
      name: "project_copy",
      columns: [{ source: "name", target: "project_name", type_code: "text" }],
    })
    await flushPromises()

    expect(create).toHaveBeenCalledWith({
      path: { connector_id: "target-1" },
      body: {
        parent_node_id: "public",
        name: "project_copy",
        source_connector_id: "connector-1",
        source_node_id: "public.projects",
        columns: [
          { source: "name", target: "project_name", type_code: "text" },
        ],
      },
    })
  })

  it("greys the commands the source withdraws over this page, and keeps them", async () => {
    // A report is the server describing what it is doing, not data somebody
    // is keeping, so it withdraws everything that would take a copy of the
    // page away (D72). The grid is told, not asked to work it out — and what
    // is withdrawn stays in its place, greyed, rather than leaving a row of a
    // different shape behind it.
    vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({
      data: { ...result(0, 2), page_commands: [] },
    } as never)
    const wrapper = mountGrid({ canQuery: true })
    await flushPromises()

    for (const command of [
      "grid-download",
      "grid-share",
      "grid-charts",
      "grid-create-table",
      "grid-query",
    ]) {
      const button = wrapper.get(`[data-testid="${command}"]`)
      expect(button.attributes("disabled")).toBeDefined()
    }
    // What is left is what reading the page needs.
    expect(wrapper.get('[data-testid="grid-filter"]').attributes("disabled")).toBeUndefined()
    expect(wrapper.find('[data-testid="grid-auto-refresh"]').exists()).toBe(true)
  })

  it("says why a withdrawn command cannot be used", async () => {
    // The reason is read off the prop: a tooltip is drawn only once something
    // hovers it, and nothing hovers in jsdom. That it opens over a disabled
    // button at all is a browser question, asserted in `grid.spec.ts`.
    vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({
      data: { ...result(0, 2), page_commands: [] },
    } as never)
    const wrapper = mountGrid({ canQuery: true })
    await flushPromises()

    const share = wrapper
      .findAllComponents(AppIconButton)
      .find((one) => one.props("icon") === "share")

    expect(String(share?.props("tooltip"))).toContain("cannot be shared")
  })

  it("offers everything to a page that says nothing about its commands", async () => {
    // Withdrawing is the source's to do, so silence is not a withdrawal: a
    // source that never learned to answer this keeps the whole toolbar, and
    // only an answer takes anything away (D72).
    const page = result(0, 2) as Record<string, unknown>
    delete page.page_commands
    vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({ data: page } as never)
    const wrapper = mountGrid({ canQuery: true })
    await flushPromises()

    for (const command of [
      "grid-download",
      "grid-share",
      "grid-charts",
      "grid-create-table",
      "grid-query",
    ]) {
      expect(wrapper.find(`[data-testid="${command}"]`).exists()).toBe(true)
    }
  })

  it("draws them when the source offers them", async () => {
    mockPages()
    const wrapper = mountGrid({ canQuery: true })
    await flushPromises()

    for (const command of [
      "grid-download",
      "grid-share",
      "grid-charts",
      "grid-create-table",
      "grid-query",
    ]) {
      expect(wrapper.find(`[data-testid="${command}"]`).exists()).toBe(true)
    }
  })

  it("opens a chart with the exact page and visible columns", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-columns"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-column-visible-id"]').trigger("click")
    await wrapper.get('[data-testid="grid-charts"]').trigger("click")

    const emitted = wrapper.findComponent(DataGrid).emitted("chart")?.[0]
    expect(emitted).toEqual([
      {
        node_id: "public.projects",
        limit: 100,
        offset: 0,
        filters: [],
        sort: [],
      },
      ["name"],
    ])
  })

  it("downloads only the current page and visible columns", async () => {
    mockPages()
    const download = vi.spyOn(ConnectorsService, "downloadPage").mockResolvedValue({
      data: new Blob(["name\nProject 1\n"], { type: "text/csv" }),
      headers: { "content-disposition": 'attachment; filename="projects.csv"' },
    } as never)
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:page")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    const wrapper = mountGrid({ title: "projects" })
    await flushPromises()

    await wrapper.get('[data-testid="grid-columns"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-column-visible-id"]').trigger("click")
    await wrapper.get('[data-testid="grid-download"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="grid-download-run"]')?.click()
    await flushPromises()

    expect(download).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { connector_id: "connector-1" },
        responseType: "blob",
        body: expect.objectContaining({
          node_id: "public.projects",
          offset: 0,
          limit: 100,
          title: "projects",
          columns: ["name"],
        }),
      })
    )
  })

  it("exports every matching row without asking the client for a blob", async () => {
    mockPages()
    const exportRows = vi.spyOn(ConnectorsService, "exportAllRows").mockResolvedValue({
      data: {
        filename: "projects.csv",
        row_count: 1201,
        download_url: "/api/v1/connectors/export-downloads/ticket",
      },
    } as never)
    let nativeHref = ""
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      nativeHref = this.href
    })
    const wrapper = mountGrid({ title: "projects" })
    await flushPromises()

    await wrapper.get('[data-testid="grid-columns"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-column-visible-id"]').trigger("click")
    await wrapper.get('[data-testid="grid-download"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="download-scope-all"]')?.click()
    document.body.querySelector<HTMLElement>('[data-testid="grid-download-run"]')?.click()
    await flushPromises()

    expect(exportRows).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        title: "projects",
        columns: ["name"],
        filters: [],
        sort: [],
      },
    })
    expect(nativeHref).toContain("/api/v1/connectors/export-downloads/ticket")
  })

  it("offers structure in the grid only when the node is describable", async () => {
    mockPages()
    const wrapper = mountGrid({ canDescribe: true })
    await flushPromises()
    expect(wrapper.find('[data-testid="grid-structure"]').exists()).toBe(true)
  })

  it("offers the source-named content representation and emits its command", async () => {
    mockPages()
    const wrapper = mountGrid({ contentTitle: "View DDL" })
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-content"]').exists()).toBe(true)
    await wrapper.get('[data-testid="grid-content"]').trigger("click")

    expect(wrapper.findComponent(DataGrid).emitted("content")).toHaveLength(1)
  })

  it("renders server columns and requests 100 rows by default", async () => {
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    expect(wrapper.get('[data-testid="grid-column-id"]').text()).toContain("id")
    expect(wrapper.get('[data-testid="grid-column-name"]').text()).toContain("name")
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Project 1")
    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ offset: 0, limit: 100 }) })
    )
  })

  it("pastes a block from the clipboard as one request", async () => {
    const page = {
      columns: [
        {
          name: "name",
          type: { sql: "text", category: "string" },
          editable: true,
          nullable: false,
        },
        {
          name: "note",
          type: { sql: "text", category: "string" },
          editable: true,
          nullable: true,
        },
      ],
      rows: [
        ["Ada", "x"],
        ["Grace", "y"],
      ],
      row_handles: ["row-0", "row-1"],
      update_supported: true,
      has_more: false,
    }
    vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({ data: page } as never)
    const update = vi.spyOn(ConnectorsService, "updateCells").mockResolvedValue({
      data: { kind: "updated", rows: [] },
    } as never)
    vi.spyOn(navigator.clipboard, "readText").mockResolvedValue("Ann\tp\r\nBob\tq")
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-cell-0-name"]').trigger("mousedown")
    document.dispatchEvent(new MouseEvent("mouseup"))
    await flushPromises()
    await wrapper.get('[data-testid="grid-paste"]').trigger("click")
    await flushPromises()

    // One request, rows rather than cells, and the block landing from the
    // selected cell.
    expect(update).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        rows: [
          {
            row_handle: "row-0",
            cells: [
              { column: "name", value: "Ann" },
              { column: "note", value: "p" },
            ],
          },
          {
            row_handle: "row-1",
            cells: [
              { column: "name", value: "Bob" },
              { column: "note", value: "q" },
            ],
          },
        ],
      },
    })
    wrapper.unmount()
  })

  it("fills the row being inserted from a copied line", async () => {
    const page = {
      columns: [
        {
          name: "id",
          type: { sql: "bigint", category: "number" },
          insertable: false,
        },
        {
          name: "name",
          type: { sql: "text", category: "string" },
          editable: true,
          insertable: true,
          nullable: false,
        },
        {
          name: "note",
          type: { sql: "text", category: "string" },
          editable: true,
          insertable: true,
          nullable: true,
        },
      ],
      rows: [["1", "Ada", "x"]],
      row_handles: ["row-0"],
      update_supported: true,
      insert_supported: true,
      has_more: false,
    }
    vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({ data: page } as never)
    const insert = vi.spyOn(ConnectorsService, "insertRow").mockResolvedValue({
      data: { values: ["2", "Ann", "p"], row_handle: "row-1" },
    } as never)
    vi.spyOn(navigator.clipboard, "readText").mockResolvedValue("9\tAnn\tp")
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-insert"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-insert-paste"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-insert-save"]').trigger("click")
    await flushPromises()

    // The identity the source fills itself is left out; the rest lands by
    // position.
    expect(insert).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        values: [
          { column: "name", value: "Ann" },
          { column: "note", value: "p" },
        ],
      },
    })
    wrapper.unmount()
  })

  it("edits only a server-declared cell with its opaque row handle", async () => {
    vi.spyOn(ConnectorsService, "fetchRows")
      .mockResolvedValueOnce({
        data: {
          columns: [
            {
              name: "name",
              type: { sql: "text", category: "string" },
              editable: true,
              nullable: false,
            },
          ],
          rows: [["Ada"]],
          row_handles: ["opaque-row"],
          update_supported: true,
          has_more: false,
        },
      } as never)
      .mockResolvedValue({
        data: {
          columns: [
            {
              name: "name",
              type: { sql: "text", category: "string" },
              editable: true,
              nullable: false,
            },
          ],
          rows: [["Grace"]],
          row_handles: ["new-row"],
          update_supported: true,
          has_more: false,
        },
      } as never)
    const update = vi.spyOn(ConnectorsService, "updateCell").mockResolvedValue({
      data: { values: ["Grace"], row_handle: "new-row" },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-cell-0-name"]').trigger("dblclick")
    await flushPromises()
    const input = document.body.querySelector<HTMLInputElement>('[data-testid="grid-edit-value"]')
    expect(input).not.toBeNull()
    input?.focus()
    input?.setSelectionRange(0, input.value.length)
    input?.dispatchEvent(new InputEvent("input", { data: "Grace", bubbles: true }))
    if (input !== null) input.value = "Grace"
    input?.dispatchEvent(new Event("input", { bubbles: true }))
    document.body.querySelector<HTMLElement>('[data-testid="grid-edit-save"]')?.click()
    await flushPromises()

    expect(update).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        row_handle: "opaque-row",
        column: "name",
        value: "Grace",
      },
    })
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Grace")
    wrapper.unmount()
  })

  it("inserts only supplied fields and leaves omitted columns to defaults", async () => {
    const insertedResult: FetchResult = {
      columns: [
        {
          name: "id",
          type: { sql: "integer", category: "number" },
          insertable: true,
          has_default: true,
        },
        {
          name: "name",
          type: { sql: "text", category: "string" },
          insertable: true,
          insert_required: true,
        },
      ],
      rows: [],
      row_handles: [],
      insert_supported: true,
      has_more: false,
    }
    vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({ data: insertedResult } as never)
    const insert = vi.spyOn(ConnectorsService, "insertRow").mockResolvedValue({
      data: { values: ["1", "Ada"], row_handle: "row-1" },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-insert"]').trigger("click")
    await flushPromises()
    expect(wrapper.get('[data-testid="grid-insert-row"]').element.tagName).toBe("TR")
    await wrapper.get('[data-testid="grid-insert-value-name"]').setValue("Ada")
    await wrapper.get('[data-testid="grid-insert-save"]').trigger("click")
    await flushPromises()

    expect(insert).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        values: [{ column: "name", value: "Ada" }],
      },
    })
    wrapper.unmount()
  })

  it("deletes a complete selected row only after confirmation", async () => {
    vi.spyOn(ConnectorsService, "fetchRows")
      .mockResolvedValueOnce({
        data: {
          columns: [{ name: "name", type: { sql: "text", category: "string" } }],
          rows: [["Ada"]],
          row_handles: ["opaque-row"],
          delete_supported: true,
          has_more: false,
        },
      } as never)
      .mockResolvedValue({
        data: {
          columns: [{ name: "name", type: { sql: "text", category: "string" } }],
          rows: [],
          row_handles: [],
          delete_supported: true,
          has_more: false,
        },
      } as never)
    const remove = vi.spyOn(ConnectorsService, "deleteRows").mockResolvedValue({
      data: { deleted: 1 },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-select-row-0"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-delete"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="confirm-accept"]')?.click()
    await flushPromises()

    expect(remove).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: { node_id: "public.projects", row_handles: ["opaque-row"] },
    })
    wrapper.unmount()
  })

  it("turns pages with an explicit server offset", async () => {
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-next"]').trigger("click")
    await flushPromises()

    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({
        body: expect.objectContaining({ offset: 100, limit: 100 }),
        query: {},
      })
    )
    expect(wrapper.get('[data-testid="grid-page-range"]').text()).toContain("Rows 101–200")
  })

  it("resets to the first page when page size changes", async () => {
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    await wrapper.get('[data-testid="grid-next"]').trigger("click")
    await flushPromises()

    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", 250)
    await flushPromises()

    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ offset: 0, limit: 250 }) })
    )
  })

  it("reload repeats the current request", async () => {
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    await wrapper.get('[data-testid="grid-next"]').trigger("click")
    await flushPromises()
    const callsBeforeReload = fetchRows.mock.calls.length

    await (wrapper.vm as unknown as { reload: () => Promise<void> }).reload()

    expect(fetchRows).toHaveBeenCalledTimes(callsBeforeReload + 1)
    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ offset: 100, limit: 100 }) })
    )
  })

  it("applies filters from page zero and persists the exact conditions", async () => {
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    await wrapper.get('[data-testid="grid-next"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-filter"]').trigger("click")
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "1")

    await wrapper.get('[data-testid="grid-filter-apply"]').trigger("click")
    await flushPromises()

    const filters = [{ column: "id", op: "eq", value: "1" }] as const
    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({
        body: expect.objectContaining({ offset: 0, filters }),
      })
    )
    expect(loadGridState("connector-1", "public.projects")?.filters).toEqual(filters)
  })

  it("uses normal and Shift sort-button clicks for one ordered server sort", async () => {
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-sort-direction-id"]').trigger("click")
    await flushPromises()
    await wrapper
      .get('[data-testid="grid-sort-direction-name"]')
      .trigger("click", { shiftKey: true })
    await flushPromises()

    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({
        body: expect.objectContaining({
          sort: [
            { column: "id", descending: false },
            { column: "name", descending: false },
          ],
        }),
      })
    )
    expect(wrapper.get('[data-testid="grid-sort-priority-id"]').text()).toBe("1")
    expect(wrapper.get('[data-testid="grid-sort-priority-name"]').text()).toBe("2")
    expect(wrapper.get('[data-testid="grid-sort-direction-id"]').attributes("data-direction")).toBe(
      "asc"
    )
  })

  it("never requests a sort for a non-sortable header", async () => {
    const fetchRows = vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({
      data: {
        columns: [
          {
            name: "payload",
            type: { sql: "jsonb", category: "json" },
            sortable: false,
            filter_operators: ["is_null"],
          },
        ],
        rows: [["{}"]],
        has_more: false,
      },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()
    const callsBeforeClick = fetchRows.mock.calls.length

    expect(wrapper.find('[data-testid="grid-sort-direction-payload"]').exists()).toBe(false)

    expect(fetchRows).toHaveBeenCalledTimes(callsBeforeClick)
  })

  it("auto fits from full current-page values and persists the width", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-resize-name"]').trigger("dblclick")

    expect(loadGridState("connector-1", "public.projects")?.columnSizing.name).toBeGreaterThan(100)
  })

  it("updates and persists a drag resize while the pointer is still down", async () => {
    saveGridState("connector-1", "public.projects", {
      columnOrder: ["id", "name"],
      columnVisibility: {},
      columnSizing: { name: 160 },
      pinnedLeft: [],
      filters: [],
      sort: [],
    })
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    const handle = wrapper.get('[data-testid="grid-resize-name"]')

    await handle.trigger("mousedown", { clientX: 100 })
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 140, bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(loadGridState("connector-1", "public.projects")?.columnSizing.name).toBe(200)
    expect(wrapper.get('[data-testid="row-grid"]').attributes("style")).toContain(
      "--grid-column-1: 200px"
    )

    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 220, bubbles: true }))
    // A second move inside the same frame is held and applied on the next one:
    // the table throttles a drag to one update per animation frame, so a
    // microtask is not long enough to see it.
    await nextFrame()
    await wrapper.vm.$nextTick()
    expect(loadGridState("connector-1", "public.projects")?.columnSizing.name).toBe(280)
    expect(wrapper.get('[data-testid="row-grid"]').attributes("style")).toContain(
      "--grid-column-1: 280px"
    )

    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 220, bubbles: true }))
    await wrapper.vm.$nextTick()

    expect(loadGridState("connector-1", "public.projects")?.columnSizing.name).toBe(280)
  })

  it("restores order, visibility, width and left pinning on remount", async () => {
    const state = {
      columnOrder: ["name", "id"],
      columnVisibility: { id: false },
      columnSizing: { name: 220 },
      pinnedLeft: ["name"],
      filters: [],
      sort: [],
    }
    saveGridState("connector-1", "public.projects", state)
    mockPages()

    const wrapper = mountGrid()
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-column-id"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="row-grid"]').attributes("style")).toContain(
      "--grid-column-1: 220px"
    )
    expect(wrapper.get('[data-testid="grid-column-name"]').classes()).toContain("data-grid__pinned")
  })

  it("keeps the pin icon visible while the column is pinned", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    const pin = wrapper.get('[data-testid="grid-pin-name"]')
    expect(pin.get(".q-icon").text()).toContain("push_pin")
    expect(pin.attributes("aria-pressed")).toBe("false")

    await pin.trigger("click")

    const unpin = wrapper.get('[data-testid="grid-pin-name"]')
    expect(unpin.get(".q-icon").text()).toContain("push_pin")
    expect(unpin.attributes("aria-pressed")).toBe("true")
    expect(unpin.classes()).toContain("data-grid__pin--active")
  })

  it("selects and extends cells with mouse and keyboard", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    const grid = wrapper.get('[data-testid="grid-focus"]')

    await wrapper.get('[data-testid="grid-cell-0-id"]').trigger("mousedown")
    document.dispatchEvent(new MouseEvent("mouseup"))
    expect(wrapper.get('[data-testid="grid-cell-0-id"]').classes()).toContain("data-grid__selected")

    await grid.trigger("keydown", { key: "ArrowRight" })
    expect(wrapper.get('[data-testid="grid-cell-0-id"]').classes()).not.toContain(
      "data-grid__selected"
    )
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').classes()).toContain(
      "data-grid__selected"
    )

    await grid.trigger("keydown", { key: "ArrowDown", shiftKey: true })
    expect(wrapper.get('[data-testid="grid-cell-1-name"]').classes()).toContain(
      "data-grid__selected"
    )
  })

  it("extends the active rectangle with Shift-click", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-cell-0-id"]').trigger("mousedown")
    document.dispatchEvent(new MouseEvent("mouseup"))
    await wrapper.get('[data-testid="grid-cell-1-name"]').trigger("mousedown", { shiftKey: true })
    document.dispatchEvent(new MouseEvent("mouseup"))

    expect(wrapper.findAll(".data-grid__selected")).toHaveLength(4)
  })

  it("selects a row, a visible column and the whole page with explicit selectors", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-select-row-0"]').trigger("click")
    expect(wrapper.findAll(".data-grid__selected")).toHaveLength(2)

    await wrapper.get('[data-testid="grid-column-select-name"]').trigger("click")
    expect(wrapper.findAll(".data-grid__selected")).toHaveLength(100)

    await wrapper.get('[data-testid="grid-select-page"]').trigger("click")
    expect(wrapper.findAll(".data-grid__selected")).toHaveLength(200)
  })

  it("copies the same raw TSV from a drag and from Ctrl+C", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    const from = wrapper.get('[data-testid="grid-cell-0-id"]')
    const to = wrapper.get('[data-testid="grid-cell-0-name"]')

    await from.trigger("mousedown")
    await to.trigger("mouseenter")
    document.dispatchEvent(new MouseEvent("mouseup"))
    await wrapper.get('[data-testid="grid-copy"]').trigger("click")
    await wrapper.get('[data-testid="grid-focus"]').trigger("keydown", {
      key: "c",
      ctrlKey: true,
    })

    expect(writeText).toHaveBeenNthCalledWith(1, "1\tProject 1")
    expect(writeText).toHaveBeenNthCalledWith(2, "1\tProject 1")
  })

  it("clears selection when the page or column structure changes", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    await wrapper.get('[data-testid="grid-cell-0-id"]').trigger("mousedown")
    document.dispatchEvent(new MouseEvent("mouseup"))

    await wrapper.get('[data-testid="grid-next"]').trigger("click")
    await flushPromises()
    expect(wrapper.findAll(".data-grid__selected")).toHaveLength(0)

    await wrapper.get('[data-testid="grid-column-select-name"]').trigger("click")
    expect(wrapper.findAll(".data-grid__selected")).toHaveLength(100)
    await wrapper.get('[data-testid="grid-pin-name"]').trigger("click")
    expect(wrapper.findAll(".data-grid__selected")).toHaveLength(0)
  })

  it("shows an initial skeleton while the first page is pending", async () => {
    vi.spyOn(ConnectorsService, "fetchRows").mockImplementation(
      () => new Promise(() => {}) as never
    )

    const wrapper = mountGrid()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="grid-skeleton"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grid-header"]').exists()).toBe(true)
  })

  it("keeps rows under an overlay while the current page refetches", async () => {
    let finish: ((value: unknown) => void) | undefined
    const fetchRows = vi
      .spyOn(ConnectorsService, "fetchRows")
      .mockResolvedValueOnce({ data: result(0, 1) } as never)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve
          }) as never
      )
    const wrapper = mountGrid()
    await flushPromises()

    vi.useFakeTimers()
    try {
      const reload = (wrapper.vm as unknown as { reload: () => Promise<void> }).reload()
      await wrapper.vm.$nextTick()
      // Not yet: a read that may still answer within a frame or two is not
      // worth drawing over the rows.
      expect(wrapper.find('[data-testid="grid-loading-overlay"]').exists()).toBe(false)

      await vi.advanceTimersByTimeAsync(400)
      expect(wrapper.find('[data-testid="grid-loading-overlay"]').exists()).toBe(true)
      expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Project 1")

      finish?.({ data: result(0, 1) })
      await reload
      expect(fetchRows).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it("says nothing about a re-read that answers at once", async () => {
    // The tab that refreshes itself every few seconds is answered in
    // milliseconds. A veil mounted over the whole grid for two frames reads
    // as the table blinking out.
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await (wrapper.vm as unknown as { reload: () => Promise<void> }).reload()
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-loading-overlay"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Project 1")
    expect(fetchRows).toHaveBeenCalledTimes(2)
  })

  it("removes prior rows after failure and retries from the safe error", async () => {
    const fetchRows = vi
      .spyOn(ConnectorsService, "fetchRows")
      .mockResolvedValueOnce({ data: result(0, 1) } as never)
      .mockRejectedValueOnce(new Error("password=secret"))
      .mockResolvedValueOnce({ data: result(0, 1) } as never)
    const wrapper = mountGrid()
    await flushPromises()

    await (wrapper.vm as unknown as { reload: () => Promise<void> }).reload()
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-cell-0-name"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="grid-error"]').text()).toContain("Could not read the rows")
    expect(wrapper.text()).not.toContain("password=secret")
    await wrapper.get('[data-testid="grid-retry"]').trigger("click")
    await flushPromises()
    expect(fetchRows).toHaveBeenCalledTimes(3)
  })

  it("does not persist a filter until the server accepts it", async () => {
    vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) =>
      (options.body.filters?.length ?? 0) > 0
        ? (Promise.reject(new Error("Query failed")) as never)
        : (Promise.resolve({ data: result(0, 1) }) as never)
    )
    const wrapper = mountGrid()
    await flushPromises()
    await wrapper.get('[data-testid="grid-filter"]').trigger("click")
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "not accepted")

    await wrapper.get('[data-testid="grid-filter-apply"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-testid="grid-error"]').text()).toContain("Could not read the rows")
    expect(loadGridState("connector-1", "public.projects")?.filters ?? []).toEqual([])
  })

  /**
   * U02: a value the source refused - `abc` for a timestamp - took the columns
   * away with the answer, and the toolbar read them as a source that filters
   * nothing. Correcting the value meant discarding the whole query.
   */
  it("keeps the filter editor open on a value the source refused", async () => {
    vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) =>
      (options.body.filters?.length ?? 0) > 0
        ? (Promise.reject(new Error("invalid input syntax for type timestamp")) as never)
        : (Promise.resolve({ data: result(0, 2) }) as never)
    )
    const wrapper = mountGrid()
    await flushPromises()
    await wrapper.get('[data-testid="grid-filter"]').trigger("click")
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "abc")
    await wrapper.get('[data-testid="grid-filter-apply"]').trigger("click")
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-error"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="grid-filter"]').attributes("disabled")).toBeUndefined()
    expect(wrapper.find('[data-testid="grid-filter-editor"]').exists()).toBe(true)

    // And the refused condition is where it was applied, to be taken out there.
    await wrapper.get('[data-testid="grid-filter-delete-0"]').trigger("click")
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-error"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Project 1")
  })

  it("blames the refusal rather than the source for what needs rows", async () => {
    vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) =>
      (options.body.filters?.length ?? 0) > 0
        ? (Promise.reject(new Error("Query failed")) as never)
        : (Promise.resolve({
            data: { ...result(0, 2), insert_supported: true },
          }) as never)
    )
    const wrapper = mountGrid()
    await flushPromises()
    const insert = () =>
      wrapper.findAllComponents(AppIconButton).find((one) => one.props("icon") === "add")
    expect(String(insert()?.props("tooltip"))).not.toContain("does not add rows")

    await wrapper.get('[data-testid="grid-filter"]').trigger("click")
    wrapper.findComponent(AppInput).vm.$emit("update:modelValue", "abc")
    await wrapper.get('[data-testid="grid-filter-apply"]').trigger("click")
    await flushPromises()

    // Off, because there are no rows - not because this source never adds one.
    expect(wrapper.get('[data-testid="grid-insert"]').attributes("disabled")).toBeDefined()
    expect(String(insert()?.props("tooltip"))).toContain("could not be read")
  })

  it("resets a persisted query that fails when the grid is reopened", async () => {
    saveGridState("connector-1", "public.projects", {
      columnOrder: ["id", "name"],
      columnVisibility: {},
      columnSizing: {},
      pinnedLeft: [],
      filters: [{ column: "id", op: "eq", value: "not accepted" }],
      sort: [],
    })
    const fetchRows = vi
      .spyOn(ConnectorsService, "fetchRows")
      .mockImplementation((options) =>
        (options.body.filters?.length ?? 0) > 0
          ? (Promise.reject(new Error("Query failed")) as never)
          : (Promise.resolve({ data: result(0, 1) }) as never)
      )
    const wrapper = mountGrid()
    await flushPromises()
    expect(wrapper.get('[data-testid="grid-error"]').text()).toContain("Could not read the rows")

    await wrapper.get('[data-testid="grid-reset-query"]').trigger("click")
    await flushPromises()

    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ filters: [], sort: [] }) })
    )
    expect(loadGridState("connector-1", "public.projects")?.filters).toEqual([])
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Project 1")
  })

  it("drops only what a renamed column left behind and goes on reading", async () => {
    // A filter and a sort name a column by name. Rename that column while the
    // tab is open — here, in another tab, or outside the application — and the
    // stored query names something the relation no longer has.
    const columns = (owner: boolean): FetchColumn[] => [
      {
        name: "id",
        type: { sql: "bigint", category: "number" as const },
        filter_operators: ["eq"],
        sortable: true,
      },
      {
        name: "name",
        type: { sql: "text", category: "string" as const },
        filter_operators: ["contains"],
        sortable: true,
      },
      ...(owner
        ? ([
            {
              name: "owner",
              type: { sql: "text", category: "string" },
              filter_operators: ["eq"],
              sortable: true,
            },
          ] as FetchColumn[])
        : []),
    ]
    const page = (owner: boolean): FetchResult => ({
      columns: columns(owner),
      rows: [owner ? ["1", "Project 1", "ann"] : ["1", "Project 1"]],
      has_more: false,
    })
    const refused = new AxiosError("Request failed with status code 422")
    refused.response = {
      status: 422,
      statusText: "",
      headers: {},
      config: {} as never,
      data: {
        detail: [{ loc: ["body"], msg: 'Relation has no column "owner"', type: "value_error" }],
      },
    }
    const kept: Filter = { column: "name", op: "contains", value: "a" }
    saveGridState("connector-1", "public.projects", {
      columnOrder: [],
      columnVisibility: {},
      columnSizing: {},
      pinnedLeft: [],
      filters: [{ column: "owner", op: "eq", value: "ann" } as Filter, kept],
      sort: [{ column: "owner", descending: true }],
    })
    let calls = 0
    const fetchRows = vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) => {
      calls += 1
      const named = [...(options.body.filters ?? []), ...(options.body.sort ?? [])]
      return named.some((item) => item.column === "owner")
        ? (Promise.reject(refused) as never)
        : (Promise.resolve({ data: page(calls === 1) }) as never)
    })

    const wrapper = mountGrid()
    await flushPromises()
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-error"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Project 1")
    // The filter on a column that is still there survives; Reset query would
    // have thrown it away with the other one.
    expect(fetchRows).toHaveBeenLastCalledWith(
      expect.objectContaining({
        body: expect.objectContaining({ filters: [kept], sort: [] }),
      })
    )
    expect(loadGridState("connector-1", "public.projects")?.filters).toEqual([kept])
    expect(loadGridState("connector-1", "public.projects")?.sort).toEqual([])
    wrapper.unmount()
  })

  it("shows an empty page while Previous stays available", async () => {
    vi.spyOn(ConnectorsService, "fetchRows").mockImplementation(
      (options) =>
        Promise.resolve({
          data:
            (options.body.offset ?? 0) === 0
              ? { ...result(0, 1), has_more: true }
              : { ...result(100, 0), has_more: false },
        }) as never
    )
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-next"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-testid="grid-empty"]').text()).toContain("No rows")
    expect(wrapper.get('[data-testid="grid-prev"]').attributes("disabled")).toBeUndefined()
  })

  it("renders typed cells and opens complex values in the full viewer", async () => {
    vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({
      data: {
        columns: [
          { name: "enabled", type: { sql: "boolean", category: "boolean" } },
          { name: "id", type: { sql: "uuid", category: "uuid" } },
          { name: "payload", type: { sql: "jsonb", category: "json" } },
        ],
        rows: [["true", "550e8400-e29b-41d4-a716-446655440000", '{"full":"value"}']],
        has_more: false,
      },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    expect(wrapper.get('[data-testid="grid-cell-0-enabled"]').text()).toBe("true")
    expect(wrapper.find('[data-testid="grid-cell-0-enabled"] .q-checkbox').exists()).toBe(false)
    expect(wrapper.get('[data-testid="grid-cell-0-id"] span').classes()).toContain(
      "data-grid__monospace"
    )

    await wrapper.get('[data-testid="grid-cell-0-payload"]').trigger("dblclick")
    await flushPromises()
    expect(document.body.textContent).toContain('{"full":"value"}')
  })

  it("offers what the source wants asked from above its rows, and opens its form", async () => {
    // Which actions belong here is the source's answer (D79): nothing on this
    // side reads the name, so the test invents one the client cannot know.
    mockPages()
    vi.spyOn(ConnectorsService, "readActions").mockResolvedValue({
      data: [
        {
          name: "create_role",
          title: "New role",
          destructive: false,
          takes_file: false,
          takes_many_files: false,
          previews: false,
          takes_set: false,
          previews_set: false,
          downloads: false,
          acts_on: "node",
          offered_in: "rows",
          icon: "person_add",
          applicable: true,
          params_schema: {
            type: "object",
            properties: { name: { type: "string", title: "Name" } },
          },
        },
        {
          name: "rename",
          title: "Rename",
          destructive: false,
          takes_file: false,
          takes_many_files: false,
          previews: false,
          takes_set: false,
          previews_set: false,
          downloads: false,
          acts_on: "node",
          offered_in: "catalog",
          applicable: true,
          params_schema: { type: "object", properties: {} },
        },
      ],
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    // The one the source asked for here, and only that one: what belongs in
    // the catalog menu stays in the catalog menu.
    expect(wrapper.find('[data-testid="grid-node-action-rename"]').exists()).toBe(false)
    const button = wrapper.get('[data-testid="grid-node-action-run-create_role"]')
    // The picture the source named, not one chosen here by the action's name.
    expect(button.text()).toContain("person_add")

    await button.trigger("click")
    await flushPromises()

    expect(document.body.textContent).toContain("New role")
  })
})

describe("what a source offers on one row", () => {
  const INSTALL = {
    name: "install_extension",
    title: "Install",
    icon: "add",
    description: "Install this on the server",
    requires: "structure",
    identified_by: "name",
    applies_when: { column: "installed", equals: "false" },
    changes_structure: true,
  }
  const REMOVE = {
    ...INSTALL,
    name: "drop_extension",
    title: "Remove",
    icon: "delete",
    destructive: true,
    applies_when: { column: "installed", equals: "true" },
  }

  function mockReport() {
    return vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({
      data: {
        columns: [
          { name: "name", type: { sql: "text", category: "string" } },
          { name: "installed", type: { sql: "boolean", category: "boolean" } },
        ],
        rows: [
          ["citext", "true"],
          ["bloom", "false"],
        ],
        has_more: false,
        // A report is a statement's answer: no row of one opens on its own.
        record_supported: false,
        record_reason: "This is a report and holds no rows of its own",
        row_commands: [INSTALL, REMOVE],
      },
    } as never)
  }

  it("puts one of the two in the corner of each row, and no way in downwards", async () => {
    mockReport()
    const wrapper = mountGrid()
    await flushPromises()

    // The row's own value decides which of the two means anything on it, and
    // the source is what said so: nothing here knows what `installed` is.
    expect(wrapper.find('[data-testid="grid-row-command-drop_extension-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grid-row-command-install_extension-0"]').exists()).toBe(
      false
    )
    expect(wrapper.find('[data-testid="grid-row-command-install_extension-1"]').exists()).toBe(
      true
    )
    expect(wrapper.find('[data-testid="grid-row-command-drop_extension-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="grid-open-row-0"]').exists()).toBe(false)
    // And nothing about them is left in the row of buttons above the page.
    expect(wrapper.find('[data-testid="grid-row-command-run-install_extension"]').exists()).toBe(
      false
    )
  })

  it("runs it with the key of the row it was pressed on", async () => {
    mockReport()
    const run = vi.spyOn(ConnectorsService, "runRowCommand").mockResolvedValue({
      data: { message: "1 extension installed", done: 1, refused: [] },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper
      .get('[data-testid="grid-row-command-install_extension-1"]')
      .trigger("click")
    await flushPromises()

    expect(run).toHaveBeenCalledWith({
      path: { connector_id: "connector-1" },
      body: {
        node_id: "public.projects",
        name: "install_extension",
        keys: ["bloom"],
      },
    })
  })

  it("keeps the way in downwards where the source did not withdraw it", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-open-row-0"]').exists()).toBe(true)
  })
})

describe("following a reference out of a row", () => {
  const keyed = {
    columns: [
      {
        name: "region_id",
        type: { sql: "bigint", category: "number" },
        sortable: true,
        filter_operators: ["eq"],
      },
      {
        name: "note",
        type: { sql: "text", category: "string" },
        sortable: true,
        filter_operators: ["eq"],
      },
    ],
    rows: [
      ["7", "first"],
      [null, "second"],
    ],
    has_more: false,
    references: [
      { name: "customers_region_fkey", columns: ["region_id"], target_title: "sales.regions" },
    ],
  }

  function mockKeyedPage() {
    return vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({ data: keyed } as never)
  }

  it("sends the whole key of that row and emits where the source points", async () => {
    mockKeyedPage()
    const follow = vi.spyOn(ConnectorsService, "followReference").mockResolvedValue({
      data: {
        kind: "rows",
        node: {
          kind: "table",
          id: "sales.regions",
          name: "regions",
          has_children: false,
          representations: [{ kind: "table", title: "View as table" }],
        },
        filters: [{ column: "id", op: "eq", value: "7" }],
      },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-follow-0-customers_region_fkey"]').trigger("click")
    await flushPromises()

    expect(follow).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          node_id: "public.projects",
          reference: "customers_region_fkey",
          direction: "outgoing",
          values: [{ column: "region_id", value: "7" }],
        },
      })
    )
    expect(wrapper.findComponent(DataGrid).emitted("follow")?.[0]?.[0]).toMatchObject({
      node: { id: "sales.regions" },
      filters: [{ column: "id", op: "eq", value: "7" }],
    })
  })

  it("marks the corner of the cell and leaves the cell's own hint alone", async () => {
    // Two tooltips used to be drawn over one another: the cell carries the
    // browser's own hint about editing, and the way out carries its own. An
    // empty `title` on the mark is what stops the browser walking up to the
    // cell for one.
    mockKeyedPage()
    const wrapper = mountGrid()
    await flushPromises()

    const mark = wrapper.get('[data-testid="grid-follow-0-customers_region_fkey"]')

    expect(mark.element.tagName).toBe("BUTTON")
    expect(mark.classes()).toContain("data-grid__follow")
    expect(mark.attributes("title")).toBe("")
    expect(mark.attributes("aria-label")).toBe("Go to sales.regions")
  })

  it("offers the way back where a key lands, and says which one was chosen", async () => {
    mockKeyedPage()
    vi.spyOn(ConnectorsService, "arrivingReferences").mockResolvedValue({
      data: [
        { name: "orders_region_fkey", columns: ["region_id"], source_title: "sales.orders" },
        { name: "shops_region_fkey", columns: ["region_id"], source_title: "sales.shops" },
      ],
    } as never)
    const follow = vi.spyOn(ConnectorsService, "followReference").mockResolvedValue({
      data: {
        kind: "rows",
        node: {
          kind: "table",
          id: "sales.shops",
          name: "shops",
          has_children: false,
          representations: [{ kind: "table", title: "View as table" }],
        },
        filters: [{ column: "region_id", op: "eq", value: "7" }],
      },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    // The mark sits on the cell the arriving keys land on, and on no other.
    expect(wrapper.find('[data-testid="grid-arriving-0-region_id"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grid-arriving-0-note"]').exists()).toBe(false)

    await wrapper.get('[data-testid="grid-arriving-0-region_id"]').trigger("click")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="menu-item-shops_region_fkey"]')?.click()
    await flushPromises()

    expect(follow).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          node_id: "public.projects",
          reference: "shops_region_fkey",
          direction: "incoming",
          values: [{ column: "region_id", value: "7" }],
        },
      })
    )
    expect(wrapper.findComponent(DataGrid).emitted("follow")?.[0]?.[0]).toMatchObject({
      node: { id: "sales.shops" },
    })
  })

  it("offers no way back out of an empty cell either", async () => {
    mockKeyedPage()
    vi.spyOn(ConnectorsService, "arrivingReferences").mockResolvedValue({
      data: [
        { name: "orders_region_fkey", columns: ["region_id"], source_title: "sales.orders" },
      ],
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-arriving-0-region_id"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grid-arriving-1-region_id"]').exists()).toBe(false)
  })

  it("draws no way out of an empty cell", async () => {
    mockKeyedPage()
    const wrapper = mountGrid()
    await flushPromises()

    expect(wrapper.find('[data-testid="grid-follow-0-customers_region_fkey"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grid-follow-1-customers_region_fkey"]').exists()).toBe(false)
  })

  it("says what the source said when a key names nothing, and opens no tab", async () => {
    mockKeyedPage()
    vi.spyOn(ConnectorsService, "followReference").mockResolvedValue({
      data: { kind: "none", reason: "This row has no value for that reference" },
    } as never)
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-follow-0-customers_region_fkey"]').trigger("click")
    await flushPromises()

    expect(wrapper.findComponent(DataGrid).emitted("follow")).toBeUndefined()
    // What was said, not where it was drawn: the card is the notification
    // log's business and this grid is mounted without one (D114).
    expect(notices().entries.value.map((entry) => entry.message).join(" "))
      .toContain("no value for that reference")
  })

  it("shows the predicate it was navigated to by, over the remembered query", async () => {
    saveGridState("connector-1", "public.projects", {
      columnOrder: ["region_id", "note"],
      columnVisibility: {},
      columnSizing: {},
      pinnedLeft: [],
      filters: [{ column: "note", op: "eq", value: "remembered" }],
      sort: [],
    })
    const fetch = mockKeyedPage()
    const wrapper = mountGrid({
      referenceFilters: [{ column: "region_id", op: "eq", value: "7" }],
    })
    await flushPromises()

    expect(fetch.mock.calls.at(-1)?.[0]?.body?.filters).toEqual([
      { column: "region_id", op: "eq", value: "7" },
    ])
    const command = wrapper
      .findAllComponents(AppIconButton)
      // By the icon rather than by the test id: the kit stopped letting
      // attributes fall through to its root so a disabled button could carry
      // its tooltip on a wrapper.
      .find((button) => button.props("icon") === "filter_alt")
    expect(command?.props("tooltip")).toBe("Filters (1)")
  })
})
