import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ref } from "vue"

import { ConnectorsService, QueriesService } from "@/client"
import { workspaceActionsKey } from "@/features/workspace/state"
import { useBottomPanel } from "@/features/workspace/useBottomPanel"

import QueriesCommand from "./QueriesCommand.vue"
import { useQueriesLibrary } from "./library"

// The real list mounts every tool, a terminal among them, which jsdom cannot draw.
vi.mock("@/features/workspace/bottomTools", () => ({
  BOTTOM_TOOLS: [{ id: "queries", title: "Queries", component: {} }],
}))

const library = useQueriesLibrary()
const panel = useBottomPanel()
const active = ref<string | null>("c1")

enableAutoUnmount(afterEach)

/** Each connection's profile, answered when the test says so. */
const answers = new Map<string, (value: unknown) => void>()

function mountCommand() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return mount(QueriesCommand, {
    global: {
      plugins: [Quasar, [VueQueryPlugin, { queryClient }]],
      provide: { [workspaceActionsKey as symbol]: { activeConnectorId: active } },
    },
  })
}

beforeEach(() => {
  vi.restoreAllMocks()
  answers.clear()
  active.value = "c1"
  library.connectorId.value = null
  panel.hide()
  vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({ data: { data: [], count: 0 } } as never)
  vi.spyOn(QueriesService, "readProfile").mockImplementation(((options: { path: { connector_id: string } }) =>
    new Promise((resolve) => { answers.set(options.path.connector_id, resolve) })) as never)
})

describe("the query library's switch", () => {
  it("aims the library when the capability lands after the press", async () => {
    const wrapper = mountCommand()
    await flushPromises()
    await wrapper.get('[data-testid="command-queries"]').trigger("click")
    expect(library.connectorId.value).toBeNull()

    answers.get("c1")?.({ data: {} })
    await flushPromises()

    expect(library.connectorId.value).toBe("c1")
  })

  it("leaves a filter set to every connection alone when the connection changes", async () => {
    const wrapper = mountCommand()
    answers.get("c1")?.({ data: {} })
    await flushPromises()
    await wrapper.get('[data-testid="command-queries"]').trigger("click")
    expect(library.connectorId.value).toBe("c1")

    library.connectorId.value = null
    active.value = "c2"
    await flushPromises()
    answers.get("c2")?.({ data: {} })
    await flushPromises()

    expect(library.connectorId.value).toBeNull()
  })
})
