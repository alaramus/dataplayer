import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query"
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { Quasar } from "quasar"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"

import { AiService } from "@/client"
import { windowsApiKey } from "@/shared/windows"

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
  document.body.innerHTML = ""
  vi.spyOn(AiService, "readModels").mockResolvedValue({ data: MODELS } as never)
  vi.spyOn(AiService, "readSettings").mockResolvedValue({ data: { keys: [] } } as never)
})

function mountSelect(modelValue: string | null, hint = true) {
  const client = new QueryClient()
  return mount(AiModelSelect, {
    props: { modelValue, hint },
    global: {
      plugins: [Quasar, [VueQueryPlugin, { queryClient: client }]],
      provide: { [windowsApiKey]: {} },
    },
  })
}

function hinted() {
  return document.body.querySelector('[data-testid="ai-model-hint"]') !== null
}

describe("the missing-model hint", () => {
  it("opens by the Model field while no model is chosen", async () => {
    const wrapper = mountSelect(null)
    await flushPromises()
    await nextTick()
    expect(hinted()).toBe(true)
    const hint = document.body.querySelector('[data-testid="ai-model-hint"]')
    expect(hint?.textContent).toContain("Model list")
    expect(hint?.textContent).toContain("API key")
    wrapper.unmount()
  })

  it("stays away with a model, and after being dismissed", async () => {
    const wrapper = mountSelect("openai:gpt-4o")
    await flushPromises()
    await nextTick()
    expect(hinted()).toBe(false)

    await wrapper.setProps({ modelValue: null })
    await flushPromises()
    await nextTick()
    expect(hinted()).toBe(true)

    document.body
      .querySelector('[data-testid="ai-model-hint-close"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await nextTick()
    expect(hinted()).toBe(false)
    await flushPromises()
    await nextTick()
    expect(hinted()).toBe(false)
    wrapper.unmount()
  })

  it("gets out of the way when the model list is reached for", async () => {
    const wrapper = mountSelect(null)
    await flushPromises()
    await nextTick()
    expect(hinted()).toBe(true)

    // A press on the field is inside the popup's anchor, so it does not
    // count as outside: without this the hint stands open under the list.
    await wrapper.get(".ai-model-select").trigger("pointerdown")
    await nextTick()
    expect(hinted()).toBe(false)
    wrapper.unmount()
  })

  it("stays quiet where choosing is the screen itself", async () => {
    const wrapper = mountSelect(null, false)
    await flushPromises()
    await nextTick()
    expect(hinted()).toBe(false)
    wrapper.unmount()
  })
})
