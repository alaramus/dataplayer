import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AiService } from "@/client"

import AiModelSelect from "./AiModelSelect.vue"

const MODELS = [
  {
    key: "openai:gpt-4o",
    name: "GPT-4o",
    provider: "openai",
    provider_label: "OpenAI",
  },
]

beforeEach(() => {
  vi.restoreAllMocks()
  setActivePinia(createPinia())
  vi.spyOn(AiService, "readModels").mockResolvedValue({ data: MODELS } as never)
  vi.spyOn(AiService, "readSettings").mockResolvedValue({ data: { keys: [] } } as never)
})

function mountSelect(modelValue: string | null, hint = true) {
  const client = new QueryClient()
  return mount(AiModelSelect, {
    props: { modelValue, hint },
    global: { plugins: [Quasar, [VueQueryPlugin, { queryClient: client }]] },
  })
}

describe("the missing-model hint", () => {
  it("opens by the Model field while no model is chosen", async () => {
    const wrapper = mountSelect(null)
    await flushPromises()
    const hint = wrapper.get('[data-testid="ai-model-hint"]')
    expect(hint.text()).toContain("Model list")
    expect(hint.text()).toContain("API key")
    wrapper.unmount()
  })

  it("stays away with a model, and after being dismissed", async () => {
    const wrapper = mountSelect("openai:gpt-4o")
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-model-hint"]').exists()).toBe(false)

    await wrapper.setProps({ modelValue: null })
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-model-hint"]').exists()).toBe(true)

    await wrapper.get('[data-testid="ai-model-hint-close"]').trigger("click")
    expect(wrapper.find('[data-testid="ai-model-hint"]').exists()).toBe(false)
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-model-hint"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("gets out of the way when the model list is reached for", async () => {

    const wrapper = mountSelect(null)
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-model-hint"]').exists()).toBe(true)

    // A press on the field is inside the popup's anchor, so it does not
    // count as outside: without this the hint stands open under the list.
    await wrapper.get(".ai-model-select").trigger("pointerdown")
    expect(wrapper.find('[data-testid="ai-model-hint"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("stays quiet where choosing is the screen itself", async () => {
    const wrapper = mountSelect(null, false)
    await flushPromises()
    expect(wrapper.find('[data-testid="ai-model-hint"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
