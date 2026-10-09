import { enableAutoUnmount, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"

import { AppSelect } from "@/shared/ui"
import { useVoiceStore } from "@/stores/voice"

import VoiceSelect from "./VoiceSelect.vue"

const IRINA = { name: "Irina", lang: "ru-RU", voiceURI: "irina" }

beforeEach(() => {
  setActivePinia(createPinia())
  document.body.innerHTML = ""
  vi.stubGlobal("speechSynthesis", {
    getVoices: () => [IRINA],
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })
})

// Hooks run last-registered first: the control is unmounted, and lets go of
// the synthesis, before the synthesis is taken away.
afterEach(() => {
  vi.unstubAllGlobals()
})
enableAutoUnmount(afterEach)

describe("the reading-voice control", () => {
  it("offers the browser voices and keeps the choice", async () => {
    const wrapper = mount(VoiceSelect, { global: { plugins: [Quasar] } })
    await nextTick()
    const field = wrapper.findComponent(AppSelect)
    const options = field.props("options") as Array<{ label: string; value: string }>
    expect(options.map((option) => option.label)).toContain("Browser default")
    expect(options.map((option) => option.label)).toContain("Irina · ru-RU")

    field.vm.$emit("update:modelValue", "irina")
    expect(useVoiceStore().voice).toBe("irina")
  })
})
