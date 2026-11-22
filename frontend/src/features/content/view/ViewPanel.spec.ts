import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { AxiosError } from "axios"
import { createPinia, setActivePinia } from "pinia"
import { Quasar } from "quasar"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"
import type { WorkspaceActions } from "@/features/workspace/state"

import ViewPanel from "./ViewPanel.vue"
import { SAMPLE_VIEW } from "./sample"

let openRepresentation = vi.fn()
let openIntent = vi.fn()
let closeTab = vi.fn()

const Host = defineComponent({
  components: { ViewPanel },
  provide() {
    return {
      [workspaceActionsKey as symbol]: {
        openRepresentation,
        openIntent,
        closeTab,
      } as unknown as WorkspaceActions,
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
      stubs: { PanelCommands: true, ActionDialog: true },
    },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
  openRepresentation = vi.fn()
  openIntent = vi.fn()
  closeTab = vi.fn()
  vi.spyOn(ConnectorsService, "readActions").mockResolvedValue({ data: [] } as never)
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

  it("offers the JSON by an icon named in the source's words, in a tab of its own (D424)", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({ data: SAMPLE_VIEW } as never)
    const wrapper = mountPanel()
    await flushPromises()

    const button = wrapper.get('[data-testid="view-show-tree"]')
    expect(button.text()).not.toContain("As JSON")
    expect(button.attributes("aria-label")).toBe("As JSON")
    await button.trigger("click")
    expect(openRepresentation).toHaveBeenCalledWith({
      connectorId: "c1",
      nodeId: "container:abc/inspect",
      title: "dp-test-web — As JSON",
      connectorName: "Docker",
      adapterType: "docker",
      representations: [{ kind: "tree", title: "As JSON" }],
      describable: false,
    })
  })

  it("uses the representation's icon when the source names one", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({ data: SAMPLE_VIEW } as never)
    const wrapper = mountPanel()
    await wrapper.setData({
      representations: [
        { kind: "view", title: "Overview" },
        { kind: "table", title: "View bindings", icon: "hub" },
      ],
    })
    await flushPromises()

    const button = wrapper.get('[data-testid="view-show-table"]')
    expect(button.html()).toContain("hub")
    expect(button.attributes("aria-label")).toBe("View bindings")
  })

  it("opens a source-declared page as a separate node tab", async () => {
    const page = {
      node_id: "container:abc/logs",
      title: "Logs",
      representations: [{ kind: "table", title: "View as table" }],
      icon: "receipt_long",
    }
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: { ...SAMPLE_VIEW, pages: [page] },
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    const button = wrapper.get('[data-testid="view-page-0"]')
    // The source's picture, its title the tooltip.
    expect(button.html()).toContain("receipt_long")
    expect(button.attributes("aria-label")).toBe("Logs")
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

  it("draws the actions the source puts over the view, by icon (D424)", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({ data: SAMPLE_VIEW } as never)
    vi.spyOn(ConnectorsService, "readActions").mockResolvedValue({
      data: [action("docker_stop", { in_view: true, icon: "stop" }), action("elsewhere", { icon: "edit" })],
    } as never)
    const wrapper = mountPanel()
    await flushPromises()

    const stop = wrapper.get('[data-testid="view-action-docker_stop"]')
    expect(stop.attributes("aria-label")).toBe("Stop it")
    expect(wrapper.find('[data-testid="view-action-elsewhere"]').exists()).toBe(false)
    await stop.trigger("click")
    expect(wrapper.findComponent({ name: "ActionDialog" }).exists()).toBe(true)
  })

  it("opens the node returned by a view action in its preferred representation", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({ data: SAMPLE_VIEW } as never)
    vi.spyOn(ConnectorsService, "readActions").mockResolvedValue({
      data: [action("rabbitmq_peek", { title: "Peek", in_view: true, icon: "visibility" })],
    } as never)
    vi.spyOn(ConnectorsService, "readNodePath").mockResolvedValue({
      data: [{
        id: "peek:%2F/orders/1",
        name: "Peek result",
        kind: "report",
        has_children: false,
        representations: [{ kind: "table", title: "View messages" }],
        describable: false,
        summarizable: false,
        description: null,
      }],
    } as never)
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="view-action-rabbitmq_peek"]').trigger("click")

    wrapper.findComponent({ name: "ActionDialog" }).vm.$emit("done", {
      done: [{
        message: "Looked in the queue",
        reload_node_ids: [],
        open_node_id: "peek:%2F/orders/1",
      }],
      failures: [],
      total: 1,
    })
    await flushPromises()

    expect(openIntent).toHaveBeenCalledWith({
      connectorId: "c1",
      nodeId: "peek:%2F/orders/1",
      view: "preferred",
      title: "Peek result",
      describable: false,
      representations: [{ kind: "table", title: "View messages" }],
      ancestors: [],
    }, {
      float: false,
    })
  })

  it("closes its tab once the node an action removed is gone (D424)", async () => {
    const read = vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({ data: SAMPLE_VIEW } as never)
    vi.spyOn(ConnectorsService, "readActions").mockResolvedValue({
      data: [action("docker_remove_container", { in_view: true, icon: "delete", destructive: true })],
    } as never)
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="view-action-docker_remove_container"]').trigger("click")

    read.mockRejectedValue(new AxiosError("gone", undefined, undefined, undefined, {
      status: 404, data: { detail: "Not found" },
    } as never))
    wrapper.findComponent({ name: "ActionDialog" }).vm.$emit("done", {
      done: [{ message: "Removed", reload_node_ids: ["containers"] }],
      failures: [],
      total: 1,
    })
    await flushPromises()

    expect(closeTab).toHaveBeenCalledWith("content:c1:container:abc/inspect:view")
  })
})

function action(name: string, extra: Record<string, unknown>) {
  return {
    name,
    title: name === "docker_stop" ? "Stop it" : name,
    destructive: false,
    takes_file: false,
    takes_many_files: false,
    previews: false,
    takes_set: false,
    previews_set: false,
    downloads: false,
    acts_on: "node",
    applies_to: ["container"],
    offered_in: "catalog",
    applicable: true,
    available_node_ids: null,
    params_schema: { type: "object", properties: {} },
    ...extra,
  }
}
