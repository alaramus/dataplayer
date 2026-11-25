import { describe, expect, it, vi } from "vitest"

import { SpeechWriter, transcriptOf, useDictation } from "./dictation"
import type { Recognition, RecognitionEvent, RecognitionResult } from "./dictation"

function result(transcript: string, isFinal: boolean): RecognitionResult {
  return { length: 1, isFinal, 0: { transcript } }
}

function event(...results: RecognitionResult[]): RecognitionEvent {
  // Built by hand rather than spread: spreading an array into an object gives
  // its length as well, and the list already says how long it is.
  const list: RecognitionEvent["results"] = { length: results.length }
  results.forEach((result, index) => { list[index] = result })
  return { resultIndex: 0, results: list }
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
    const dictation = useDictation(() => {}, () => null)

    dictation.toggle()

    expect(dictation.supported).toBe(false)
    expect(dictation.listening.value).toBe(false)
  })

  it("hands over everything heard while it listens", () => {
    const engine = fake()
    const written: string[] = []
    const dictation = useDictation((heard) => written.push(heard), () => engine)

    dictation.toggle()
    engine.onresult?.(event(result("count the ", true), result("orders", false)))

    expect(dictation.listening.value).toBe(true)
    expect(engine.start).toHaveBeenCalled()
    expect(written).toEqual(["count the orders"])
  })

  it("does not send an empty interim result to the text writer", () => {
    const engine = fake()
    const written: string[] = []
    const dictation = useDictation((heard) => written.push(heard), () => engine)

    dictation.toggle()
    engine.onresult?.(event(result("", false)))

    expect(written).toEqual([])
  })

  it("stops when pressed again, and when the browser ends the session itself", () => {
    const engine = fake()
    const dictation = useDictation(() => {}, () => engine)

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
    const dictation = useDictation(() => {}, () => engine)

    dictation.toggle()
    engine.onerror?.({ error: "no-speech" })
    engine.onerror?.({ error: "not-allowed" })

    expect(dictation.failure.value).toBe("not-allowed")
    expect(dictation.listening.value).toBe(false)
  })
})

describe("words spoken into a text", () => {
  it("takes the place of the selection and revises what it wrote there", () => {
    const speech = new SpeechWriter()
    speech.begin({ from: 7, to: 11 })

    expect(speech.write(20, 0, "count the ord")).toEqual({ from: 7, to: 11, text: "count the ord" })
    // The recogniser revises the open end rather than adding to it.
    expect(speech.write(20, 0, "count the orders")).toEqual({
      from: 7,
      to: 20,
      text: "count the orders",
    })
  })

  it("carries on at the caret with only the words not yet written", () => {
    const speech = new SpeechWriter()
    speech.begin({ from: 0, to: 0 })
    speech.write(0, 0, "one two")
    speech.interrupt()

    // Somebody typed somewhere else; a place that is gone must not be written
    // over, and the words already down must not be said again.
    expect(speech.write(30, 30, "one two three")).toEqual({ from: 30, to: 30, text: " three" })
  })

  it("keeps a place inside a text that has shrunk under it", () => {
    const speech = new SpeechWriter()
    speech.begin({ from: 20, to: 25 })

    expect(speech.write(4, 0, "tail")).toEqual({ from: 4, to: 4, text: "tail" })
  })

  it("says nothing twice when an interrupted session hears the same words again", () => {
    const speech = new SpeechWriter()
    speech.begin({ from: 0, to: 0 })
    speech.write(0, 0, "the ledger")
    speech.interrupt()

    expect(speech.write(10, 10, "the ledger")).toEqual({ from: 10, to: 10, text: "" })
  })
})
