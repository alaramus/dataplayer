import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"

import AiModelHint from "./AiModelHint.vue"

describe("the missing-model popup", () => {
  it("names the Model list and the provider key, and closes", async () => {
    const wrapper = mount(AiModelHint, {
      props: { modelValue: true },
      global: { plugins: [Quasar] },
    })
    const hint = wrapper.get('[data-testid="ai-model-hint"]')
    expect(hint.text()).toContain("Model list")
    expect(hint.text()).toContain("API key")
    await wrapper.get('[data-testid="ai-model-hint-close"]').trigger("click")
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]])
    wrapper.unmount()
  })
})
