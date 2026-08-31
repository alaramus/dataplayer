import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"

import MarkdownPanel from "./MarkdownPanel.vue"

const openRepresentation = vi.fn()
let registry = createReloadRegistry()

const Host = defineComponent({
  components: { MarkdownPanel },
  props: { panel: { type: Object, required: true } },
  setup() {
    provideReloadRegistry(registry)
  },
  template: `<MarkdownPanel v-bind="panel" />`,
})

function mountPanel(overrides: Record<string, unknown> = {}) {
  return mount(Host, {
    props: {
      panel: {
        panelId: "content:c1:guide.md:markdown",
        connectorId: "c1",
        nodeId: "guide.md",
        title: "guide.md",
        connectorName: "my files",
        adapterType: "file",
        sourceTitle: "View as text",
        ...overrides,
      },
    },
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
      provide: {
        [workspaceActionsKey as symbol]: { openRepresentation },
      },
    },
  })
}

function document(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      kind: "markdown",
      text: "# Title\n\nA paragraph.\n",
      truncated: false,
      notice: null,
      ...overrides,
    },
  } as never
}

beforeEach(() => {
  vi.restoreAllMocks()
  openRepresentation.mockClear()
  registry = createReloadRegistry()
})

describe("the rendered document panel", () => {
  it("renders the document rather than its source", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(document())

    const wrapper = mountPanel()
    await flushPromises()

    const rendered = wrapper.get('[data-testid="markdown-document"]')
    expect(rendered.find("h1").text()).toBe("Title")
    expect(rendered.text()).not.toContain("# Title")
  })

  it("asks for the markdown representation of the node it was opened on", async () => {
    const read = vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(document())

    mountPanel()
    await flushPromises()

    expect(read.mock.calls[0]?.[0]?.body).toEqual({
      node_id: "guide.md",
      representation: "markdown",
    })
  })

  it("says a cut document is only its beginning", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(document({ truncated: true }))

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="markdown-truncated"]').text()).toContain(
      "only its beginning"
    )
  })

  it("counts the images it did not request, and asks before requesting them", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({ text: "![one](https://example.test/a.png)\n\n![two](https://example.test/b.png)" })
    )

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="markdown-document"]').html()).not.toContain("example.test")
    expect(wrapper.text()).toContain("2 image(s)")

    await wrapper.get('[data-testid="markdown-allow-remote"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-testid="markdown-document"]').html()).toContain(
      "example.test/a.png"
    )
  })

  it("opens the source in the editor under the name the source gave it", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(document())

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="markdown-view-source"]').trigger("click")

    expect(openRepresentation).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeId: "guide.md",
        representations: [{ kind: "text", title: "View as text" }],
      })
    )
  })

  it("states what went wrong instead of showing an empty document", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockRejectedValue(new Error("no such file"))

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-testid="content-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="markdown-document"]').exists()).toBe(false)
  })
})
