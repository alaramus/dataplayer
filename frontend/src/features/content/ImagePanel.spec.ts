import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { client } from "@/client/client.gen"
import { createReloadRegistry, provideReloadRegistry } from "@/features/workspace/reloadable"

import ImagePanel from "./ImagePanel.vue"

let registry = createReloadRegistry()

const Host = defineComponent({
  components: { ImagePanel },
  setup() {
    provideReloadRegistry(registry)
  },
  template: `
    <ImagePanel
      panel-id="content:c1:logo.png:image"
      connector-id="c1"
      node-id="logo.png"
      title="logo.png"
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
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { retry: false, gcTime: 0 } },
            }),
          },
        ],
      ],
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  registry = createReloadRegistry()
  client.setConfig({ baseURL: "http://example.test" })
})

afterEach(() => {
  client.setConfig({ baseURL: "" })
})

describe("the bounded image panel", () => {
  it("renders only the verified preview URL and states its source metadata", async () => {
    vi.spyOn(ConnectorsService, "readContent").mockResolvedValue({
      data: {
        kind: "image",
        filename: "logo.png",
        media_type: "image/png",
        size_bytes: 68,
        width: 1,
        height: 1,
        preview_url: "/api/v1/connectors/content-files/preview-ticket",
      },
    } as never)

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.get('[data-testid="image-preview"]').attributes("src")).toBe(
      "http://example.test/api/v1/connectors/content-files/preview-ticket"
    )
    expect(wrapper.get('[data-testid="image-details"]').text()).toContain("1 × 1")
  })
})
