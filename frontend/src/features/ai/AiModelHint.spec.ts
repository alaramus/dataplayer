import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { describe, expect, it } from "vitest"
import { nextTick } from "vue"

import AiModelHint from "./AiModelHint.vue"

describe("the missing-model popup", () => {
  it("names the Model list and the provider key, and closes", async () => {
    const wrapper = mount(AiModelHint, {
      props: { modelValue: true },
      global: { plugins: [Quasar] },
    })
    await nextTick()
    const hint = document.body.querySelector('[data-testid="ai-model-hint"]')
    expect(hint?.textContent).toContain("Model list")
    expect(hint?.textContent).toContain("API key")
    document.body
      .querySelector('[data-testid="ai-model-hint-close"]')
      ?.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    await nextTick()
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]])
    wrapper.unmount()
  })
})
