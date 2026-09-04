import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, ref } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"

import RowsPanel from "./RowsPanel.vue"

const openRepresentation = vi.fn()
const showInPlace = vi.fn()
const workspace = {
  followTarget: ref(null),
  takeFollow: vi.fn(() => null),
  sharedTarget: ref(null),
  takeShared: vi.fn(() => null),
  openRepresentation,
  showInPlace,
  openStructure: vi.fn(),
  openChart: vi.fn(),
  followReference: vi.fn(),
}

const DataGridStub = {
  props: { contentTitle: { type: String, default: "" } },
  emits: ["content", "describe", "chart", "follow"],
  template: `
    <button data-testid="rows-content" :data-title="contentTitle" @click="$emit('content')">
      content
    </button>
  `,
}

const Host = defineComponent({
  components: { RowsPanel },
  setup() {
    provideReloadRegistry(createReloadRegistry())
  },
  template: `
    <RowsPanel
      panel-id="rows:c1:public.orders"
      connector-id="c1"
      node-id="public.orders"
      title="orders"
      connector-name="local pg"
      adapter-type="postgres"
      :describable="true"
      :representations="[
        { kind: 'table', title: 'View as table' },
        { kind: 'sql', title: 'View DDL' },
      ]"
    />
  `,
})

beforeEach(() => {
  vi.clearAllMocks()
})

const SHEETS = [
  {
    kind: "dataset",
    id: "budget.xlsx/1",
    name: "Revenue",
    describable: true,
    representations: [{ kind: "table", title: "View as table" }],
  },
  {
    kind: "dataset",
    id: "budget.xlsx/2",
    name: "People",
    describable: true,
    representations: [{ kind: "table", title: "View as table" }],
  },
]

/** A tab on a workbook, which is a tab on its first sheet with the rest
    behind a select. */
const Workbook = {
  components: { RowsPanel },
  setup() {
    provideReloadRegistry(createReloadRegistry())
  },
  template: `
    <RowsPanel
      panel-id="rows:c1:budget.xlsx"
      connector-id="c1"
      node-id="budget.xlsx"
      title="budget.xlsx"
      connector-name="files"
      adapter-type="file"
      :describable="false"
      container-id="budget.xlsx"
      :representations="[{ kind: 'table', title: 'View as table' }]"
    />
  `,
}

function mounted(component: unknown) {
  return mount(component as never, {
    global: {
      plugins: [
        Quasar,
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { retry: false, gcTime: 0 } },
            }),
          },
        ],
      ],
      provide: { [workspaceActionsKey as symbol]: workspace },
      stubs: { DataGrid: DataGridStub },
    },
  })
}

describe("a rows panel over one of several tables in a file", () => {
  it("offers the others and shows the chosen one in the same tab", async () => {
    // A spreadsheet is one file with several tables in it. Being sent back to
    // the catalog to walk into a file to reach the second of them is what made
    // it feel like a folder (D51).
    vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: SHEETS,
    } as never)
    const wrapper = mounted(Workbook)
    await flushPromises()

    const switcher = wrapper.get('[data-testid="sheet-switcher"]')
    // The one being read is marked, the way a tab strip marks a tab.
    expect(switcher.get('[data-testid="sheet-Revenue"]').attributes("aria-selected")).toBe(
      "true"
    )

    await switcher.get('[data-testid="sheet-People"]').trigger("click")

    expect(showInPlace).toHaveBeenCalledWith(
      "rows:c1:budget.xlsx",
      expect.objectContaining({
        nodeId: "budget.xlsx/2",
        title: "People",
        // The sheet's own answers rather than the file's: a sheet states its
        // columns and can be described, and the workbook cannot.
        describable: true,
        containerId: "budget.xlsx",
      })
    )
  })

  it("offers nothing where the node is not one of several", async () => {
    // A table of a database belongs to no container of tables, and the reading
    // that would answer for one is the root of the catalog: every table in a
    // connection offered the files of its root as its sheets, because a
    // disabled query still reads whatever is under its key.
    const listing = vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({
      data: SHEETS,
    } as never)
    const wrapper = mounted(Host)
    await flushPromises()

    expect(wrapper.find('[data-testid="sheet-switcher"]').exists()).toBe(false)
    expect(listing).not.toHaveBeenCalled()
  })
})

describe("a rows panel with another source representation", () => {
  it("opens the chosen content first and retains the table alternative", async () => {
    const wrapper = mount(Host, {
      global: {
        // The panel asks the source what it can do, so it needs the client
        // every panel has in the application.
        plugins: [
          Quasar,
          [
            VueQueryPlugin,
            {
              queryClient: new QueryClient({
                defaultOptions: { queries: { retry: false, gcTime: 0 } },
              }),
            },
          ],
        ],
        provide: { [workspaceActionsKey as symbol]: workspace },
        stubs: { DataGrid: DataGridStub },
      },
    })

    expect(wrapper.get('[data-testid="rows-content"]').attributes("data-title")).toBe("View DDL")
    await wrapper.get('[data-testid="rows-content"]').trigger("click")

    expect(openRepresentation).toHaveBeenCalledWith({
      connectorId: "c1",
      nodeId: "public.orders",
      title: "orders",
      connectorName: "local pg",
      adapterType: "postgres",
      representations: [
        { kind: "sql", title: "View DDL" },
        { kind: "table", title: "View as table" },
      ],
      describable: true,
    })
  })
})
