import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { workspaceActionsKey } from "@/features/workspace/state"

import ContentPanel from "./ContentPanel.vue"

const openRows = vi.fn()

function mountPanel(representation: "text" | "json" | "jsonl" = "json") {
  return mount(ContentPanel, {
    props: {
      panelId: `content:c1:file:${representation}`,
      connectorId: "c1",
      nodeId: representation === "jsonl" ? "events.jsonl" : "people.json",
      title: representation === "jsonl" ? "events.jsonl" : "people.json",
      connectorName: "my files",
      adapterType: "file",
      representation,
      tableTitle: "View as table",
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
        [workspaceActionsKey as symbol]: { openRows },
      },
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  openRows.mockReset()
})

describe("the file content viewer", () => {
  it("renders a JSON tree without rounding numeric text", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: {
        kind: "json",
        value: {
          kind: "object",
          entries: [{ name: "id", value: { kind: "number", value: "10000000000000001" } }],
        },
      },
    } as never)

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="json-content"]').text()).toContain("10000000000000001")
  })

  it("reveals a wide JSON branch in bounded chunks", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: {
        kind: "json",
        value: {
          kind: "array",
          items: Array.from({ length: 101 }, (_, index) => ({
            kind: "number",
            value: String(index),
          })),
        },
      },
    } as never)

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="json-content"]').text()).not.toContain('"100":')
    await wrapper.get('[data-testid="json-show-more"]').trigger("click")
    expect(wrapper.get('[data-testid="json-content"]').text()).toContain('"100":')
  })

  it("keeps invalid JSON in the JSON viewer with the parser notice", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: {
        kind: "json",
        value: null,
        source_text: '{"id" 1}',
        notice: "This file is not valid JSON (line 1 column 7).",
      },
    } as never)

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="json-source"]').text()).toContain('{"id" 1}')
    expect(wrapper.get('[data-testid="content-notice"]').text()).toContain("not valid JSON")
  })

  it("opens the alternative table only after its button is pressed", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: { kind: "json", value: { kind: "array", items: [] } },
    } as never)

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('[data-testid="content-view-table"]').trigger("click")

    expect(openRows).toHaveBeenCalledWith({
      connectorId: "c1",
      nodeId: "people.json",
      title: "people.json",
      connectorName: "my files",
      adapterType: "file",
      describable: false,
    })
  })

  it("pages JSONL as records and keeps their physical line numbers", async () => {
    const read = vi.spyOn(ConnectorsService, "readContent")
    read.mockResolvedValueOnce({
      data: {
        kind: "jsonl",
        items: [
          {
            line_number: 3,
            value: { kind: "object", entries: [] },
          },
        ],
        has_more: true,
        offset: 0,
      },
    } as never)
    read.mockResolvedValueOnce({
      data: { kind: "jsonl", items: [], has_more: false, offset: 50 },
    } as never)

    const wrapper = mountPanel("jsonl")
    await flushPromises()
    expect(wrapper.get('[data-testid="jsonl-content"]').text()).toContain("Line 3")
    await wrapper.get('[data-testid="content-next"]').trigger("click")
    await flushPromises()

    expect(read.mock.calls[1]?.[0].body).toMatchObject({ offset: 1, limit: 50 })
  })
})
