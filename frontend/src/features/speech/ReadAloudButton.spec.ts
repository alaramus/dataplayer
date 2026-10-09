import { mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { Quasar } from "quasar"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useReadAloud } from "./readAloud"
import ReadAloudButton from "./ReadAloudButton.vue"

class FakeUtterance {
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  voice: unknown = null
  constructor(public text: string) {}
}

const spoken: FakeUtterance[] = []

function stubSpeech() {
  vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance)
  vi.stubGlobal("speechSynthesis", {
    speak: (utterance: FakeUtterance) => spoken.push(utterance),
    cancel: vi.fn(),
    getVoices: () => [],
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })
}

beforeEach(() => {
  spoken.length = 0
  setActivePinia(createPinia())
  stubSpeech()
})

afterEach(() => {
  useReadAloud().stop()
  vi.unstubAllGlobals()
})

function listenButton(wrapper: ReturnType<typeof mount>) {
  return wrapper.get('[data-testid="file-listen"]')
}

describe("the read-aloud button", () => {
  it("reads plain text as it is, keeping code marks", async () => {
    const wrapper = mount(ReadAloudButton, {
      props: { text: "SELECT * FROM orders", testid: "file-listen" },
      global: { plugins: [Quasar] },
    })

    await listenButton(wrapper).trigger("click")

    expect(spoken.map((one) => one.text)).toEqual(["SELECT * FROM orders"])
  })

  it("strips Markdown only where the caller says so", async () => {
    const wrapper = mount(ReadAloudButton, {
      props: {
        text: "**Hello** [there](https://example.test)",
        stripMarkdown: true,
        testid: "file-listen",
      },
      global: { plugins: [Quasar] },
    })

    await listenButton(wrapper).trigger("click")

    expect(spoken.map((one) => one.text)).toEqual(["Hello there"])
  })

  it("reads the stop in red while its own text is being read", async () => {
    const wrapper = mount(ReadAloudButton, {
      props: { text: "A file", testid: "file-listen" },
      global: { plugins: [Quasar] },
    })

    await listenButton(wrapper).trigger("click")
    expect(listenButton(wrapper).attributes("aria-label")).toBe("Stop reading aloud")
    expect(listenButton(wrapper).classes()).toContain("read-aloud--speaking")

    await listenButton(wrapper).trigger("click")
    expect(useReadAloud().speaking.value).toBeNull()
  })

  it("keeps saying stop when its text changes while it is read", async () => {
    const wrapper = mount(ReadAloudButton, {
      props: { text: "A file", testid: "file-listen" },
      global: { plugins: [Quasar] },
    })

    await listenButton(wrapper).trigger("click")
    await wrapper.setProps({ text: "A file, edited" })
    expect(listenButton(wrapper).attributes("aria-label")).toBe("Stop reading aloud")

    await listenButton(wrapper).trigger("click")
    expect(useReadAloud().speaking.value).toBeNull()
    expect(spoken).toHaveLength(1)
  })
})
