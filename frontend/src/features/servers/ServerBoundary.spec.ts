import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { Quasar } from "quasar"
import { computed, h, ref } from "vue"
import { beforeEach, describe, expect, it, vi } from "vitest"

import ServerBoundary from "./ServerBoundary.vue"

const answer = ref<true | undefined>(undefined)
const failure = ref<Error | null>(null)

vi.mock("./api", () => ({
  useActiveServerCheck: () => ({
    data: answer,
    error: failure,
    isPending: computed(() => answer.value === undefined && failure.value === null),
    isError: computed(() => failure.value !== null),
    isFetching: computed(() => false),
    refetch: () => undefined,
  }),
}))

vi.mock("vue-router", () => ({ useRoute: () => ({ name: "workspace" }) }))

function boundary() {
  return mount(ServerBoundary, {
    slots: { default: () => h("main", "the application") },
    // The switcher is a screen of its own with queries behind it; what is
    // under test is which of the three states the boundary draws.
    global: { plugins: [Quasar], stubs: { ServerSwitcher: true } },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  answer.value = undefined
  failure.value = null
})

describe("what is on screen before the server has answered", () => {
  it("says nothing about the connection while it is still being checked", async () => {
    // A reload used to draw the whole "cannot connect" card for the fraction
    // of a second the first check takes.
    const wrapper = boundary()
    await flushPromises()

    expect(wrapper.find('[data-testid="server-connecting"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain("Connect to DataPlayer")
    expect(wrapper.text()).not.toContain("Retry connection")
    wrapper.unmount()
  })

  it("offers the card once the server has refused", async () => {
    failure.value = new Error("Could not reach a compatible DataPlayer server.")
    const wrapper = boundary()
    await flushPromises()

    expect(wrapper.find('[data-testid="server-connecting"]').exists()).toBe(false)
    expect(wrapper.text()).toContain("Connect to DataPlayer")
    wrapper.unmount()
  })

  it("hands the application through once it has answered", async () => {
    answer.value = true
    const wrapper = boundary()
    await flushPromises()

    expect(wrapper.text()).toContain("the application")
    wrapper.unmount()
  })
})
