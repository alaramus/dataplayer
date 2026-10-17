import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent, ref } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"
import { workspaceActionsKey } from "@/features/workspace/state"

import MarkdownPanel from "./MarkdownPanel.vue"

const openRepresentation = vi.fn()
const revealInCatalog = vi.fn()
const documentTarget = ref(null)
const takeDocumentTarget = vi.fn().mockReturnValue(null)
let registry = createReloadRegistry()

const Host = defineComponent({
  components: { MarkdownPanel },
  props: { panel: { type: Object, required: true } },
  setup() {
    provideReloadRegistry(registry)
  },
  template: `<MarkdownPanel v-bind="panel" />`,
})

function mountPanel(overrides: Record<string, unknown> = {}, options: { attachTo?: HTMLElement } = {}) {
  return mount(Host, {
    ...options,
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
        [workspaceActionsKey as symbol]: {
          openRepresentation,
          revealInCatalog,
          documentTarget,
          takeDocumentTarget,
        },
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
  revealInCatalog.mockClear()
  takeDocumentTarget.mockReset().mockReturnValue(null)
  documentTarget.value = null
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

  it("builds a duplicate-safe table of contents and navigates from it", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({ text: "# One\n\n## Two\n\n# One" })
    )

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="markdown-contents"]').text()).toContain("Two")
    expect(wrapper.find('[data-testid="markdown-document"] #one').exists()).toBe(true)
    expect(wrapper.find('[data-testid="markdown-document"] #one-2').exists()).toBe(true)
    await wrapper.get('[data-testid="markdown-heading-two"]').trigger("click")
    expect(wrapper.get("#two").attributes("tabindex")).toBe("-1")
  })

  it("searches visible prose and callouts without searching a code payload", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({
        text: [
          "# Search",
          "Find this phrase.",
          "```json",
          '"find stays payload"',
          "```",
          "```summary",
          "Find this callout.",
          "```",
        ].join("\n"),
      })
    )

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="markdown-search-toggle"]').trigger("click")
    await wrapper.get('[data-testid="markdown-search"]').setValue("find")
    await flushPromises()

    expect(wrapper.get('[data-testid="markdown-search-position"]').text()).toBe("1/2")
    expect(wrapper.findAll("mark[data-search-highlight]")).toHaveLength(2)
    await wrapper.get('[data-testid="markdown-search-next"]').trigger("click")
    expect(wrapper.get('[data-testid="markdown-search-position"]').text()).toBe("2/2")
  })

  it("keeps the document search behind one button until it is opened", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(document())

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-testid="markdown-search"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="markdown-search-position"]').exists()).toBe(false)
    await wrapper.get('[data-testid="markdown-search-toggle"]').trigger("click")

    expect(wrapper.find('[data-testid="markdown-search"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="markdown-search-position"]').exists()).toBe(true)
  })

  it("clears the document search when it is closed again", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({ text: "# Search\n\nFind this phrase." })
    )

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="markdown-search-toggle"]').trigger("click")
    await wrapper.get('[data-testid="markdown-search"]').setValue("find")
    await flushPromises()
    expect(wrapper.findAll("mark[data-search-highlight]").length).toBeGreaterThan(0)

    await wrapper.get('[data-testid="markdown-search-toggle"]').trigger("click")
    await flushPromises()

    expect(wrapper.find('[data-testid="markdown-search"]').exists()).toBe(false)
    expect(wrapper.findAll("mark[data-search-highlight]")).toHaveLength(0)
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

    expect(wrapper.get('[data-testid="markdown-truncated"]').text()).toContain("only its beginning")
  })

  it("counts the images it did not request, and asks before requesting them", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({ text: "![one](https://example.test/a.png)\n\n![two](https://example.test/b.png)" })
    )

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="markdown-document"]').html()).not.toContain("example.test")
    expect(wrapper.text()).toContain("2 images in this document")

    await wrapper.get('[data-testid="markdown-allow-remote"]').trigger("click")
    await flushPromises()

    expect(wrapper.get('[data-testid="markdown-document"]').html()).toContain("example.test/a.png")
  })

  it("folds the whole side column away, the image option with the contents", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({ text: "# Title\n\n![one](https://example.test/a.png)" })
    )

    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-testid="markdown-allow-remote"]').exists()).toBe(true)
    await wrapper.get('[data-testid="markdown-toggle-contents"]').trigger("click")

    expect(wrapper.find('[data-testid="markdown-contents"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="markdown-allow-remote"]').exists()).toBe(false)
  })

  it("offers the fold for a document with blocked images and no headings", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({ text: "![one](https://example.test/a.png)" })
    )

    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.get('[data-testid="markdown-toggle-contents"]').text()).toContain("Contents")
    await wrapper.get('[data-testid="markdown-toggle-contents"]').trigger("click")

    expect(wrapper.find('[data-testid="markdown-allow-remote"]').exists()).toBe(false)
  })

  it("puts the caret in the search it opens, and Escape closes it", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(document())

    // `document` is this file's response builder; the page is window.document.
    const attached = mountPanel({}, { attachTo: window.document.body })
    await flushPromises()
    await attached.get('[data-testid="markdown-search-toggle"]').trigger("click")
    await flushPromises()

    const input = attached.get('[data-testid="markdown-search"]')
    expect(window.document.activeElement).toBe(input.element)
    await input.trigger("keydown", { key: "Escape" })
    expect(attached.find('[data-testid="markdown-search"]').exists()).toBe(false)
    attached.unmount()
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

  it("opens a relative link from the source-issued catalog node", async () => {
    const current = {
      kind: "file",
      id: "opaque-guide",
      name: "guide.md",
      size_bytes: 10,
      representations: [{ kind: "markdown", title: "View as document" }],
    }
    const target = {
      kind: "file",
      id: "opaque-notes",
      name: "notes.md",
      size_bytes: 10,
      representations: [{ kind: "markdown", title: "View as document" }],
    }
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue(
      document({ text: "[Open the notes](notes.md#details)" })
    )
    vi.spyOn(ConnectorsService, "readNodePath").mockResolvedValue({ data: [current] } as never)
    vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({ data: [target] } as never)

    const wrapper = mountPanel({ nodeId: "opaque-guide" })
    await flushPromises()
    await wrapper.get('[data-relative-link="notes.md#details"]').trigger("click")
    await flushPromises()

    expect(openRepresentation).toHaveBeenCalledWith(
      expect.objectContaining({
        nodeId: "opaque-notes",
        fragment: "details",
        representations: target.representations,
      })
    )
  })

  it("loads a relative image only through its declared verified preview", async () => {
    const current = {
      kind: "file",
      id: "opaque-guide",
      name: "guide.md",
      size_bytes: 10,
      representations: [{ kind: "markdown", title: "View as document" }],
    }
    const picture = {
      kind: "file",
      id: "opaque-picture",
      name: "picture.png",
      size_bytes: 10,
      representations: [{ kind: "image", title: "View image" }],
    }
    vi.spyOn(ConnectorsService, "readContent").mockImplementation(async (input) =>
      input.body.representation === "markdown"
        ? document({ text: "![Local](picture.png)" })
        : ({
            data: {
              kind: "image",
              filename: "picture.png",
              media_type: "image/png",
              size_bytes: 10,
              width: 2,
              height: 2,
              preview_url: "/api/v1/connectors/content-files/ticket",
            },
          } as never)
    )
    vi.spyOn(ConnectorsService, "readNodePath").mockResolvedValue({ data: [current] } as never)
    vi.spyOn(ConnectorsService, "readCatalog").mockResolvedValue({ data: [picture] } as never)

    const wrapper = mountPanel({ nodeId: "opaque-guide" })
    await flushPromises()
    await flushPromises()

    expect(wrapper.get('img[alt="Local"]').attributes("src")).toContain(
      "/api/v1/connectors/content-files/ticket"
    )
    expect(ConnectorsService.readContent).toHaveBeenCalledWith(
      expect.objectContaining({
        body: { node_id: "opaque-picture", representation: "image" },
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
