import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { FetchRequest } from "@/client"
import { withWindowHost } from "@/shared/testing/windows"

import RecordView from "./RecordView.vue"

const REQUEST: FetchRequest = {
  node_id: "public.projects",
  limit: 2,
  offset: 0,
  filters: [],
  sort: [],
}

const PAGE = {
  columns: [
    {
      name: "id",
      type: { sql: "bigint", category: "number" },
      sortable: true,
      filter_operators: ["eq"],
    },
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
    ["1", "7", "first"],
    ["2", null, "second"],
  ],
  has_more: true,
  references: [
    { name: "projects_region_fkey", columns: ["region_id"], target_title: "sales.regions" },
  ],
}

const MODEL = {
  node_id: "public.projects",
  schema_name: "public",
  name: "projects",
  kind: "table",
  columns: [
    { position: 1, name: "id", type: { sql: "bigint", category: "number" }, nullable: false },
    {
      position: 2,
      name: "region_id",
      type: { sql: "bigint", category: "number" },
      nullable: true,
    },
    { position: 3, name: "note", type: { sql: "text", category: "string" }, nullable: true },
  ],
  constraints: [
    { kind: "primary_key", name: "projects_pkey", columns: ["id"] },
    {
      kind: "foreign_key",
      name: "projects_region_fkey",
      columns: ["region_id"],
      target_schema: "sales",
      target_relation: "regions",
      target_columns: ["id"],
    },
  ],
  indexes: [],
}

function mountView(describable = true) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(
    withWindowHost(RecordView, {
      connectorId: "connector-1",
      nodeId: "public.projects",
      describable,
      request: REQUEST,
      index: 0,
    }),
    {
      global: {
        plugins: [[Quasar, { plugins: { Dialog, Notify } }], [VueQueryPlugin, { queryClient }]],
      },
    }
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
  vi.spyOn(ConnectorsService, "fetchRows").mockImplementation(
    (options: unknown) =>
      Promise.resolve({
        data: {
          ...PAGE,
          rows:
            ((options as { body: FetchRequest }).body.offset ?? 0) === 0
              ? PAGE.rows
              : [["3", "7", "third"]],
          has_more: ((options as { body: FetchRequest }).body.offset ?? 0) === 0,
        },
      }) as never
  )
  vi.spyOn(ConnectorsService, "arrivingReferences").mockResolvedValue({ data: [] } as never)
  vi.spyOn(ConnectorsService, "readRelationModel").mockResolvedValue({ data: MODEL } as never)
})

describe("one row read downwards", () => {
  it("draws every column of the row with what the source says about it", async () => {
    const wrapper = mountView()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain("region_id")
    expect(text).toContain("bigint")
    expect(wrapper.get('[data-testid="record-value-note"]').text()).toBe("first")
    // The keys come from the relation model, which is the only thing that
    // knows them; a page of rows says nothing about a primary key.
    expect(wrapper.get('[data-testid="record-badge-primary_key"]').text()).toBe("PK")
    expect(wrapper.get('[data-testid="record-number"]').text()).toBe("Row 1")
    wrapper.unmount()
  })

  it("walks to the next row of the same page without reading it again", async () => {
    const read = vi.mocked(ConnectorsService.fetchRows)
    const wrapper = mountView()
    await flushPromises()
    const before = read.mock.calls.length

    await wrapper.get('[data-testid="record-next"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-testid="record-number"]').text()).toBe("Row 2")
    expect(wrapper.get('[data-testid="record-value-note"]').text()).toBe("second")
    expect(read.mock.calls.length).toBe(before)
    wrapper.unmount()
  })

  it("crosses into the next page when the row after is on it", async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-testid="record-next"]').trigger("click")
    await flushPromises()

    // The last row of the first page; the next one is a page away.
    await wrapper.get('[data-testid="record-next"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-testid="record-number"]').text()).toBe("Row 3")
    expect(wrapper.get('[data-testid="record-value-note"]').text()).toBe("third")
    expect(ConnectorsService.fetchRows).toHaveBeenCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ offset: 2 }) })
    )
    wrapper.unmount()
  })

  it("stops at the first row and at the last", async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(
      wrapper.get('[data-testid="record-previous"]').attributes("disabled")
    ).toBeDefined()
    wrapper.unmount()
  })

  it("follows a key of the row it is showing", async () => {
    const follow = vi.spyOn(ConnectorsService, "followReference").mockResolvedValue({
      data: {
        kind: "rows",
        node: { kind: "table", id: "sales.regions", name: "regions", has_children: false, representations: [] },
        filters: [{ column: "id", op: "eq", value: "7" }],
      },
    } as never)
    const wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-testid="record-follow-region_id"]').trigger("click")
    await flushPromises()

    expect(follow).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          node_id: "public.projects",
          reference: "projects_region_fkey",
          direction: "outgoing",
          values: [{ column: "region_id", value: "7" }],
        },
      })
    )
    expect(wrapper.findComponent(RecordView).emitted("follow")?.length).toBe(1)
    wrapper.unmount()
  })

  it("asks nothing of a source that describes nothing", async () => {
    const wrapper = mountView(false)
    await flushPromises()

    expect(ConnectorsService.readRelationModel).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="record-badge-primary_key"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="record-value-note"]').text()).toBe("first")
    wrapper.unmount()
  })
})
