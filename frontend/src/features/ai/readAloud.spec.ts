import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"

import { useVoiceStore } from "@/stores/voice"

import { useReadAloud } from "./readAloud"

class FakeUtterance {
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  voice: unknown = null
  constructor(public text: string) {}
}

const spoken: FakeUtterance[] = []
const IRINA = { name: "Irina", lang: "ru-RU", voiceURI: "irina" }

beforeEach(() => {
  spoken.length = 0
  setActivePinia(createPinia())
  vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance)
  vi.stubGlobal("speechSynthesis", {
    speak: (utterance: FakeUtterance) => spoken.push(utterance),
    cancel: vi.fn(),
    getVoices: () => [IRINA],
  })
})

afterEach(() => {
  useReadAloud().stop()
  vi.unstubAllGlobals()
})

describe("reading a message aloud", () => {
  it("is one voice for every chat: another message takes over, the same one stops", () => {
    const quick = useReadAloud()
    const agent = useReadAloud()

    quick.listen("First answer")
    expect(agent.speaking.value).toBe("First answer")
    agent.listen("Second answer")
    expect(quick.speaking.value).toBe("Second answer")
    agent.listen("Second answer")
    expect(quick.speaking.value).toBeNull()
    expect(spoken.map((one) => one.text)).toEqual(["First answer", "Second answer"])
  })

  it("stops saying stop when the voice ends on its own", () => {
    const voice = useReadAloud()
    voice.listen("An answer")
    spoken[0]?.onend?.()
    expect(voice.speaking.value).toBeNull()
  })

  it("reads in the chosen voice, or the default when it is gone", () => {
    useVoiceStore().setVoice("irina")
    useReadAloud().listen("An answer")
    expect(spoken[0]?.voice).toEqual(IRINA)

    useVoiceStore().setVoice("a voice of another machine")
    useReadAloud().listen("Another answer")
    expect(spoken[1]?.voice).toBeNull()
  })
})
