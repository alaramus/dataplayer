import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { FetchResult } from "@/client"
import { AppSelect } from "@/shared/ui"
import { AppInput } from "@/shared/ui"
import { withWindowHost } from "@/shared/testing/windows"

import DataGrid from "./DataGrid.vue"
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
  }
}

function mockPages() {
  return vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) => {
    const body = options.body
    return Promise.resolve({ data: result(body.offset ?? 0, body.limit ?? 100) }) as never
  })
}

function mountGrid(props: { title?: string; canDescribe?: boolean } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(withWindowHost(DataGrid, {
    connectorId: "connector-1",
    nodeId: "public.projects",
    ...props,
  }), {
    global: {
      plugins: [[Quasar, { plugins: { Dialog, Notify } }], [VueQueryPlugin, { queryClient }]],
    },
  })
}

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
})

describe("the basic data grid", () => {
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

  it("offers structure in the grid only when the node is describable", async () => {
    mockPages()
    const wrapper = mountGrid({ canDescribe: true })
    await flushPromises()
    expect(wrapper.get('[data-testid="grid-structure"]').text()).toContain("Structure")
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
    const input = document.body.querySelector<HTMLInputElement>(
      '[data-testid="grid-edit-value"]'
    )
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
      expect.objectContaining({ body: expect.objectContaining({ offset: 100, limit: 100 }) })
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

  it("uses normal and Shift header clicks for one ordered server sort", async () => {
    const fetchRows = mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-column-id"]').trigger("click")
    await flushPromises()
    await wrapper.get('[data-testid="grid-column-name"]').trigger("click", { shiftKey: true })
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

    await wrapper.get('[data-testid="grid-column-payload"]').trigger("click")
    await flushPromises()

    expect(fetchRows).toHaveBeenCalledTimes(callsBeforeClick)
  })

  it("auto fits from full current-page values and persists the width", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()

    await wrapper.get('[data-testid="grid-resize-name"]').trigger("dblclick")

    expect(loadGridState("connector-1", "public.projects")?.columnSizing.name).toBeGreaterThan(
      100
    )
  })

  it("commits a drag resize only when the pointer is released", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    const handle = wrapper.get('[data-testid="grid-resize-name"]')

    await handle.trigger("mousedown", { clientX: 100 })
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 220, bubbles: true }))
    expect(loadGridState("connector-1", "public.projects")?.columnSizing.name).toBeUndefined()

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

  it("selects and extends cells with mouse and keyboard", async () => {
    mockPages()
    const wrapper = mountGrid()
    await flushPromises()
    const grid = wrapper.get('[data-testid="grid-focus"]')

    await wrapper.get('[data-testid="grid-cell-0-id"]').trigger("mousedown")
    document.dispatchEvent(new MouseEvent("mouseup"))
    expect(wrapper.get('[data-testid="grid-cell-0-id"]').classes()).toContain(
      "data-grid__selected"
    )

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
    await wrapper
      .get('[data-testid="grid-cell-1-name"]')
      .trigger("mousedown", { shiftKey: true })
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

    const reload = (wrapper.vm as unknown as { reload: () => Promise<void> }).reload()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="grid-loading-overlay"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="grid-cell-0-name"]').text()).toBe("Project 1")

    finish?.({ data: result(0, 1) })
    await reload
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
        ? Promise.reject(new Error("Query failed")) as never
        : Promise.resolve({ data: result(0, 1) }) as never
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

  it("resets a persisted query that fails when the grid is reopened", async () => {
    saveGridState("connector-1", "public.projects", {
      columnOrder: ["id", "name"],
      columnVisibility: {},
      columnSizing: {},
      pinnedLeft: [],
      filters: [{ column: "id", op: "eq", value: "not accepted" }],
      sort: [],
    })
    const fetchRows = vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) =>
      (options.body.filters?.length ?? 0) > 0
        ? Promise.reject(new Error("Query failed")) as never
        : Promise.resolve({ data: result(0, 1) }) as never
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

  it("shows an empty page while Previous stays available", async () => {
    vi.spyOn(ConnectorsService, "fetchRows").mockImplementation((options) =>
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
})
