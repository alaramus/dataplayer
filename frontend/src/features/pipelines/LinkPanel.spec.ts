import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PipelinesService } from "@/client"
import type { PasteOffer } from "@/client"

import LinkPanel from "./LinkPanel.vue"
import { linkFromOffer } from "./links"

enableAutoUnmount(afterEach)

const intoTable: PasteOffer = { kind: "rows_new_relation", title: "Into a new table", available: true, workflow: "new-relation" }
const link = linkFromOffer("l1", { card_id: "sales", node_id: "public.orders" }, { card_id: "lab", node_id: "public" }, intoTable)

function mountPanel(autoOpen: boolean) {
  return mount(LinkPanel, {
    props: {
      link,
      from: { connectorId: "db", end: link.source },
      to: { connectorId: "lab", end: link.target },
      name: () => "end",
      label: () => "orders",
      pipelineId: "p1",
      chain: "",
      prepare: async () => true,
      place: undefined,
      linkRun: undefined,
      run: null,
      past: false,
      autoOpen,
    },
    global: {
      plugins: [Quasar, [VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) }]],
      stubs: { CreateTableDialog: true, ImportDialog: true },
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(PipelinesService, "readLinkOffers").mockResolvedValue({ data: { offers: [intoTable] } } as never)
})

describe("the link's own window", () => {
  it("opens again when the view raises it again, after it was cancelled", async () => {
    const wrapper = mountPanel(true)
    await flushPromises()
    expect(wrapper.findComponent({ name: "CreateTableDialog" }).exists()).toBe(true)
    expect(wrapper.emitted("autoOpened")).toHaveLength(1)

    // The view lowers the flag on hearing it, and the window is cancelled.
    await wrapper.setProps({ autoOpen: false })
    wrapper.findComponent({ name: "CreateTableDialog" }).vm.$emit("update:modelValue", false)
    await flushPromises()
    expect(wrapper.findComponent({ name: "CreateTableDialog" }).exists()).toBe(false)

    // A run that failed on this link raises it again.
    await wrapper.setProps({ autoOpen: true })
    await flushPromises()
    expect(wrapper.findComponent({ name: "CreateTableDialog" }).exists()).toBe(true)
    expect(wrapper.emitted("autoOpened")).toHaveLength(2)
  })
})
