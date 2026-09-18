import { describe, expect, it, vi } from "vitest"

import { transcriptOf, useDictation } from "./dictation"
import type { Recognition, RecognitionEvent, RecognitionResult } from "./dictation"

function result(transcript: string, isFinal: boolean): RecognitionResult {
  return { length: 1, isFinal, 0: { transcript } }
}

function event(...results: RecognitionResult[]): RecognitionEvent {
  return { resultIndex: 0, results: { length: results.length, ...results } }
}

function fake(): Recognition {
  return {
    lang: "",
    continuous: false,
    interimResults: false,
    start: vi.fn(),
    stop: vi.fn(),
    onresult: null,
    onerror: null,
    onend: null,
  }
}

describe("what was heard", () => {
  it("keeps settled words and the ones still being revised together", () => {
    expect(transcriptOf(event(result("Show me ", true), result("the ord", false)))).toBe(
      "Show me the ord"
    )
  })

  it("reads every result, not only the ones since the last event", () => {
    // Chrome re-sends earlier results, and taking only the newest lost them.
    expect(transcriptOf({ resultIndex: 1, results: { length: 2, 0: result("one ", true), 1: result("two", true) } })).toBe("one two")
  })
})

describe("dictation", () => {
  it("says it cannot listen where the browser has no listener", () => {
    const dictation = useDictation(() => {}, () => {}, () => null)

    dictation.toggle()

    expect(dictation.supported).toBe(false)
    expect(dictation.listening.value).toBe(false)
  })

  it("hands over everything heard while it listens", () => {
    const engine = fake()
    const written: string[] = []
    const dictation = useDictation((heard) => written.push(heard), () => {}, () => engine)

    dictation.toggle()
    engine.onresult?.(event(result("count the ", true), result("orders", false)))

    expect(dictation.listening.value).toBe(true)
    expect(engine.start).toHaveBeenCalled()
    expect(written).toEqual(["count the orders"])
  })

  it("stops when pressed again, and when the browser ends the session itself", () => {
    const engine = fake()
    const dictation = useDictation(() => {}, () => {}, () => engine)

    dictation.toggle()
    dictation.toggle()
    expect(engine.stop).toHaveBeenCalled()
    expect(dictation.listening.value).toBe(false)

    dictation.toggle()
    engine.onend?.()
    expect(dictation.listening.value).toBe(false)
  })

  it("reports a refused microphone but not a silence", () => {
    const engine = fake()
    const reasons: string[] = []
    const dictation = useDictation(() => {}, (reason) => reasons.push(reason), () => engine)

    dictation.toggle()
    engine.onerror?.({ error: "no-speech" })
    engine.onerror?.({ error: "not-allowed" })

    expect(reasons).toEqual(["not-allowed"])
    expect(dictation.listening.value).toBe(false)
  })
})
