import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ConnectorsService } from "@/client"
import { AppSelect } from "@/shared/ui"

import NodePicker from "./NodePicker.vue"

beforeEach(() => {
  vi.restoreAllMocks()
})

const schema = { id: "demo_lab", name: "demo_lab", kind: "schema", has_children: true, representations: [] }
const table = {
  id: "demo_lab.organizations",
  name: "organizations",
  kind: "table",
  has_children: false,
  representations: [{ kind: "table", title: "View as table" }],
}

async function mountPicker() {
  vi.spyOn(ConnectorsService, "readConnectors").mockResolvedValue({
    data: { data: [{ id: "c1", name: "Source", enabled: true, adapter_type: "postgres" }], count: 1 },
  } as never)
  vi.spyOn(ConnectorsService, "readCatalog").mockImplementation((async (options: {
    query?: { node_id?: string }
  }) => ({ data: options.query?.node_id === "demo_lab" ? [table] : [schema] })) as never)
  vi.spyOn(ConnectorsService, "fetchRows").mockResolvedValue({
    data: { columns: [{ name: "id" }] },
  } as never)
  const wrapper = mount(NodePicker, {
    props: { testid: "pick" },
    global: { plugins: [Quasar, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
  await flushPromises()
  wrapper.findComponent(AppSelect).vm.$emit("update:modelValue", "c1")
  await flushPromises()
  return wrapper
}

describe("NodePicker", () => {
  it("steps back from a chosen table to its level, then up the trail", async () => {
    const wrapper = await mountPicker()
    const find = (id: string) => wrapper.find(`[data-testid="pick-${id}"]`)

    await find("node-demo_lab").trigger("click")
    await flushPromises()
    await find("node-organizations").trigger("click")
    await flushPromises()
    expect(wrapper.emitted("pick")?.at(-1)?.[0]).toMatchObject({ node: { name: "organizations" } })
    expect(find("where").text()).toBe("demo_lab / organizations")
    expect(find("node-organizations").exists()).toBe(false)

    await find("back").trigger("click")
    await flushPromises()
    expect(wrapper.emitted("pick")?.at(-1)).toEqual([null])
    expect(find("where").text()).toBe("demo_lab")
    expect(find("node-organizations").exists()).toBe(true)

    await find("back").trigger("click")
    await flushPromises()
    expect(find("where").text()).toBe("Pick a node")
    expect(find("node-demo_lab").exists()).toBe(true)
    expect(find("back").exists()).toBe(false)
  })
})
