import { mount } from "@vue/test-utils"
import { defineComponent, ref } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"

import RowsPanel from "./RowsPanel.vue"

const openRepresentation = vi.fn()
const workspace = {
  followTarget: ref(null),
  takeFollow: vi.fn(() => null),
  openRepresentation,
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

describe("a rows panel with another source representation", () => {
  it("opens the chosen content first and retains the table alternative", async () => {
    const wrapper = mount(Host, {
      global: {
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
