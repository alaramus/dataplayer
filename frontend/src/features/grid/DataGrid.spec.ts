import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { FetchResult } from "@/client"
import { AppSelect } from "@/shared/ui"
import { AppInput } from "@/shared/ui"

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

function mountGrid() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(DataGrid, {
    props: { connectorId: "connector-1", nodeId: "public.projects" },
    global: { plugins: [Quasar, [VueQueryPlugin, { queryClient }]] },
  })
}

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe("the basic data grid", () => {
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
})
