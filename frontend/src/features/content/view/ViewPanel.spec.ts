import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"
import type { WorkspaceActions } from "@/features/workspace/state"

import ViewPanel from "./ViewPanel.vue"
import { SAMPLE_VIEW } from "./sample"

let switchRepresentation = vi.fn()
let openRepresentation = vi.fn()

const Host = defineComponent({
  components: { ViewPanel },
  provide() {
    return {
      [workspaceActionsKey as symbol]: { switchRepresentation, openRepresentation } as unknown as WorkspaceActions,
    }
  },
  setup() {
    provideReloadRegistry(createReloadRegistry())
  },
  data: () => ({
    representations: [
      { kind: "view", title: "Overview" },
      { kind: "tree", title: "As JSON" },
    ],
  }),
  template: `
    <ViewPanel
      panel-id="content:c1:container:abc/inspect:view"
      connector-id="c1"
      node-id="container:abc/inspect"
      title="dp-test-web"
      connector-name="Docker"
      adapter-type="docker"
      :representations="representations"
    />
  `,
})

function mountPanel() {
  return mount(Host, {
    global: {
      plugins: [
        Quasar,
        [VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) }],
      ],
      stubs: { PanelCommands: true },
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  switchRepresentation = vi.fn()
  openRepresentation = vi.fn()
})

describe("a node opened on its view (D419)", () => {
  it("asks for the view and draws its header and blocks", async () => {
    const read = vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({ data: SAMPLE_VIEW } as never)
    const wrapper = mountPanel()
    await flushPromises()

    expect(read.mock.calls[0]?.[0].body).toEqual({ node_id: "container:abc/inspect", representation: "view" })
    expect(wrapper.get('[data-testid="view-title"]').text()).toBe("shop-web-1")
    expect(wrapper.get('[data-testid="view-state"]').text()).toBe("healthy")
    expect(wrapper.findAll('[data-testid="view-section"]')).toHaveLength(4)
    // The source's word for what this is, not this screen's.
    expect(wrapper.text()).toContain("Overview")
  })

  it("offers the JSON by the source's title and switches this tab to it", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({ data: SAMPLE_VIEW } as never)
    const wrapper = mountPanel()
    await flushPromises()

    const button = wrapper.get('[data-testid="view-show-tree"]')
    expect(button.text()).toContain("As JSON")
    await button.trigger("click")
    expect(switchRepresentation).toHaveBeenCalledWith("content:c1:container:abc/inspect:view", "tree")
  })

  it("opens a source-declared page as a separate node tab", async () => {
    const page = {
      node_id: "container:abc/logs",
      title: "Logs",
      representations: [{ kind: "table", title: "View as table" }],
    }
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: { ...SAMPLE_VIEW, pages: [page] },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    const button = wrapper.get('[data-testid="view-page-0"]')
    expect(button.text()).toContain("Logs")
    await button.trigger("click")
    expect(openRepresentation).toHaveBeenCalledWith({
      connectorId: "c1",
      nodeId: "container:abc/logs",
      title: "dp-test-web — Logs",
      connectorName: "Docker",
      adapterType: "docker",
      representations: page.representations,
      describable: false,
    })
  })
})
