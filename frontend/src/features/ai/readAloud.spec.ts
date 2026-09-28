import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useReadAloud } from "./readAloud"

class FakeUtterance {
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(public text: string) {}
}

const spoken: FakeUtterance[] = []

beforeEach(() => {
  spoken.length = 0
  vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance)
  vi.stubGlobal("speechSynthesis", {
    speak: (utterance: FakeUtterance) => spoken.push(utterance),
    cancel: vi.fn(),
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
})
