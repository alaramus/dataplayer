import { afterEach, describe, expect, it, vi } from "vitest"
import { nextTick } from "vue"

import { speechSupported, useVoices, voiceLabel } from "./voices"

const IRINA = { name: "Irina", lang: "ru-RU", voiceURI: "irina" }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("the browser voices", () => {
  it("names a voice by who it is and which language it reads", () => {
    expect(voiceLabel(IRINA)).toBe("Irina · ru-RU")
    expect(voiceLabel({ name: "Default", lang: "" })).toBe("Default")
  })

  it("is absent where there is no synthesis", () => {
    vi.stubGlobal("speechSynthesis", undefined as never)
    expect(speechSupported()).toBe(false)
    expect(useVoices().voices.value).toEqual([])
  })

  it("reads the list once it arrives", async () => {
    // Chrome's first read is usually empty; the list lands later.
    let list: unknown[] = []
    const heard: Array<() => void> = []
    vi.stubGlobal("speechSynthesis", {
      getVoices: () => list,
      addEventListener: (_: string, refresh: () => void) => heard.push(refresh),
      removeEventListener: vi.fn(),
    })
    const { voices } = useVoices()
    expect(voices.value).toEqual([])
    list = [IRINA]
    heard[0]?.()
    await nextTick()
    expect(voices.value).toEqual([IRINA])
  })
})
