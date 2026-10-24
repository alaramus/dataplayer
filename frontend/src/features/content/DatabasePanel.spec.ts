import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"

import DatabasePanel from "./DatabasePanel.vue"

let registry = createReloadRegistry()

const Host = defineComponent({
  components: { DatabasePanel },
  setup() {
    provideReloadRegistry(registry)
  },
  template: `
    <DatabasePanel
      panel-id="content:c1:data/shop.db:database"
      connector-id="c1"
      node-id="data/shop.db"
      title="shop.db"
    />
  `,
})

function mountPanel() {
  return mount(Host, {
    global: {
      plugins: [
        Quasar,
        [
          VueQueryPlugin,
          { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }) },
        ],
      ],
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  registry = createReloadRegistry()
})

describe("a database file opened from a file source (D262)", () => {
  it("lists what the file holds, with what was counted and what was not", async () => {
    const read = vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: {
        kind: "database",
        engine: "SQLite 3.50.4",
        size_bytes: 57344,
        total: 2,
        relations: [
          { name: "items", kind: "table", row_estimate: 1200 },
          { name: "cheap", kind: "view", row_estimate: null },
        ],
      },
    } as never)

    const wrapper = mountPanel()
    await flushPromises()

    expect(read.mock.calls[0]?.[0].body).toEqual({ node_id: "data/shop.db", representation: "database" })
    expect(wrapper.get('[data-testid="database-details"]').text()).toBe("SQLite 3.50.4 · 56.0 KB · 2 relations")
    const table = wrapper.get('[data-testid="database-relations"]').text()
    expect(table).toContain("items")
    expect(table).toContain("~1200")
    expect(table).toContain("view")
    expect(table).toContain("N/A")
    expect(wrapper.find('[data-testid="database-cut"]').exists()).toBe(false)
  })

  it("says when the list was cut", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: {
        kind: "database",
        engine: "SQLite 3.50.4",
        size_bytes: 1,
        total: 1500,
        relations: [{ name: "t1", kind: "table", row_estimate: null }],
      },
    } as never)

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="database-cut"]').text()).toContain("1 of 1500")
  })
})
