import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Dialog, Notify, Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { adapterTypesKey, connectorsKey } from "@/features/connectors/api"
import { withWindowHost } from "@/shared/testing/windows"

import CreateTableDialog from "./CreateTableDialog.vue"

function mountDialog() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: Number.POSITIVE_INFINITY },
    },
  })
  // Reproduce opening from a screen that has already loaded the connector
  // list. The first connector is therefore selected during component setup.
  queryClient.setQueryData(connectorsKey, {
    data: [
      {
        id: "database-1",
        name: "Database",
        adapter_type: "postgres",
        config: {},
        enabled: true,
        access: "own",
      },
    ],
    count: 1,
  })
  // And the types those connections are of. Which of them can take a new
  // relation is read off the source's own capabilities (D2), so a dialog that
  // has not been told any offers no destination at all.
  queryClient.setQueryData(adapterTypesKey, [
    {
      name: "postgres",
      title: "PostgreSQL",
      category: "sql",
      description: "",
      capabilities: [{ group: "manage", title: "Create a relation from rows", code: "create_relation" }],
      options_schema: {},
      catalog_shape: "list",
    },
  ])
  return mount(
    withWindowHost(CreateTableDialog, {
      modelValue: true,
      sourceTitle: "customers.csv",
      sourceColumns: [
        { name: "id", type: { sql: "text", category: "string" } },
      ],
      running: false,
      error: "",
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
})

describe("the initial create-table destination", () => {
  it("loads schemas for the first connector without making the user switch away", async () => {
    const readCatalog = vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: [
        {
          id: "public",
          kind: "schema",
          name: "public",
          has_children: true,
          is_system: false,
          representations: [],
        },
      ],
    } as never)
    const readOptions = vi
      .spyOn(ConnectorsService, "newRelationOptions")
      .mockResolvedValue({
        data: {
          supported: true,
          column_type_options: [{ code: "text", title: "Text" }],
        },
      } as never)

    const wrapper = mountDialog()
    await flushPromises()

    expect(readCatalog).toHaveBeenCalledWith({
      path: { connector_id: "database-1" },
      query: {},
    })
    expect(readOptions).toHaveBeenCalledWith({
      path: { connector_id: "database-1" },
      body: { parent_node_id: "public" },
    })
    wrapper.unmount()
  })
})
