import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import type { FetchColumn } from "@/client"
import { AppSelect } from "@/shared/ui"
import { withWindowHost } from "@/shared/testing/windows"

import ImportDialog from "./ImportDialog.vue"

const TARGET_COLUMNS: FetchColumn[] = [
  {
    name: "organization_id",
    type: { sql: "bigint", category: "number" },
    insertable: true,
  },
  { name: "label", type: { sql: "text", category: "string" }, insertable: true },
]

function mountDialog(extra: Record<string, unknown> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return mount(
    withWindowHost(ImportDialog, {
      modelValue: true,
      connectorId: "target-1",
      nodeId: "public.tags",
      targetColumns: TARGET_COLUMNS,
      running: false,
      error: "",
      ...extra,
    }),
    {
      global: {
        plugins: [
          [Quasar, { plugins: { Dialog, Notify } }],
          [VueQueryPlugin, { queryClient }],
        ],
      },
    }
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(window, "scrollTo").mockImplementation(() => undefined)
  vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
    data: {
      data: [
        {
          id: "source-1",
          name: "files",
          adapter_type: "file",
          config: {},
          enabled: true,
          access: "own",
        },
      ],
      count: 1,
    },
  } as never)
  vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
    data: [
      {
        id: "sample.tsv",
        kind: "file",
        name: "sample.tsv",
        has_children: false,
        size_bytes: 20,
        representations: [{ kind: "table", title: "View as table" }],
      },
    ],
  } as never)
  vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({
    data: {
      columns: [
        { name: "id", type: { sql: "text", category: "string" } },
        { name: "name", type: { sql: "text", category: "string" } },
      ],
      rows: [["1", "one"]],
      has_more: false,
    },
  } as never)
})

describe("bringing rows in from another source", () => {
  it("pairs columns by hand and sends both sides as they were chosen", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewImport").mockResolvedValue({
      data: { columns: ["organization_id", "label"], rows: [["1", "one"]], more: false },
    } as never)
    const wrapper = mountDialog()
    await flushPromises()

    // The source, then the file, then one pairing per target column.
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", "source-1")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="grid-import-node-sample.tsv"]')?.click()
    await flushPromises()

    const selects = wrapper.findAllComponents(AppSelect)
    // The first is the source; the rest are one per target column, in order.
    selects[1]?.vm.$emit("update:modelValue", "id")
    selects[2]?.vm.$emit("update:modelValue", "name")
    await flushPromises()

    document.body.querySelector<HTMLElement>('[data-testid="grid-import-preview"]')?.click()
    await flushPromises()

    expect(preview).toHaveBeenCalledWith({
      path: { connector_id: "target-1" },
      body: {
        node_id: "public.tags",
        source_connector_id: "source-1",
        source_node_id: "sample.tsv",
        columns: [
          { source: "id", target: "organization_id" },
          { source: "name", target: "label" },
        ],
      },
    })
    wrapper.unmount()
  })

  it("asks for nothing until a file and a pairing are chosen", async () => {
    const wrapper = mountDialog()
    await flushPromises()

    const run = document.body.querySelector<HTMLButtonElement>('[data-testid="grid-import-run"]')
    expect(run?.disabled).toBe(true)
    wrapper.unmount()
  })

  it("selects a database table instead of treating its id as another catalog level", async () => {
    vi.mocked(ConnectorsService.readConnectors).mockResolvedValue({
      data: {
        data: [
          {
            id: "source-1",
            name: "database",
            adapter_type: "postgres",
            config: {},
            enabled: true,
            access: "own",
          },
        ],
        count: 1,
      },
    } as never)
    const readCatalog = vi.mocked(ConnectorsService.readCatalog)
    readCatalog
      .mockReset()
      .mockResolvedValueOnce({
        data: [
          {
            id: "demo_lab",
            kind: "schema",
            name: "demo_lab",
            has_children: true,
            is_system: false,
            representations: [],
          },
        ],
      } as never)
      .mockResolvedValueOnce({
        data: [
          {
            id: "demo_lab.tasks",
            kind: "table",
            name: "tasks",
            has_children: false,
            row_count_estimate: 4,
            is_system: false,
            representations: [{ kind: "table", title: "View as table" }],
          },
        ],
      } as never)
    const fetchRows = vi.mocked(ConnectorsService.fetchRows)

    const wrapper = mountDialog()
    await flushPromises()
    wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", "source-1")
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="grid-import-node-demo_lab"]')?.click()
    await flushPromises()
    document.body.querySelector<HTMLElement>('[data-testid="grid-import-node-tasks"]')?.click()
    await flushPromises()

    expect(readCatalog.mock.calls.map(([request]) => request.query)).toEqual([
      {},
      { node_id: "demo_lab" },
    ])
    expect(fetchRows).toHaveBeenCalledWith({
      path: { connector_id: "source-1" },
      body: { node_id: "demo_lab.tasks", limit: 1 },
    })
    expect(document.body.querySelector('[data-testid="grid-import-trouble"]')).toBeNull()
    wrapper.unmount()
  })

  it("pairs a source a Paste brought, with nothing to pick", async () => {
    const preview = vi.spyOn(ConnectorsService, "previewImport").mockResolvedValue({
      data: { columns: ["label"], rows: [["one"]], more: false },
    } as never)
    const wrapper = mountDialog({
      source: {
        connectorId: "source-1",
        nodeId: "sample.tsv",
        label: "sample.tsv",
        columns: [{ name: "label", type: { sql: "text", category: "string" } }],
      },
      targetLabel: "tags",
    })
    await flushPromises()

    // One select per target column and none for a source: it is known.
    expect(wrapper.findAllComponents(AppSelect)).toHaveLength(TARGET_COLUMNS.length)
    expect(document.body.textContent).toContain("From sample.tsv, into tags")
    document.body.querySelector<HTMLElement>('[data-testid="grid-import-preview"]')?.click()
    await flushPromises()

    // The same-named column is paired to start with.
    expect(preview).toHaveBeenCalledWith({
      path: { connector_id: "target-1" },
      body: {
        node_id: "public.tags",
        source_connector_id: "source-1",
        source_node_id: "sample.tsv",
        columns: [{ source: "label", target: "label" }],
      },
    })
    wrapper.unmount()
  })
})
