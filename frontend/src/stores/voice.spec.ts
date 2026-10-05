import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

import { useVoiceStore, VOICE_KEY } from "./voice"

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.removeItem(VOICE_KEY)
})

describe("the reading voice", () => {
  it("starts at the browser default and keeps a choice", () => {
    const voice = useVoiceStore()
    expect(voice.voice).toBe("")

    voice.setVoice("Google русский")
    expect(voice.voice).toBe("Google русский")
    expect(localStorage.getItem(VOICE_KEY)).toBe("Google русский")

    voice.setVoice("")
    expect(localStorage.getItem(VOICE_KEY)).toBeNull()
  })

  it("reads back what was chosen before", () => {
    localStorage.setItem(VOICE_KEY, "Google русский")
    expect(useVoiceStore().voice).toBe("Google русский")
  })
})
