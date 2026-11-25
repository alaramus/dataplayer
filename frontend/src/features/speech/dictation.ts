import { ref } from "vue"
import type { Ref } from "vue"

/**
 * Speaking text instead of typing it, through the browser's own listener.
 *
 * As much of the Web Speech API as this app uses, declared here: the DOM types
 * shipped with TypeScript do not describe `SpeechRecognition`, and an `any`
 * would take the checking off the one place the API is touched.
 */
export interface RecognitionAlternative {
  transcript: string
}

export interface RecognitionResult {
  readonly length: number
  isFinal: boolean
  [index: number]: RecognitionAlternative
}

export interface RecognitionEvent {
  resultIndex: number
  results: { readonly length: number; [index: number]: RecognitionResult }
}

export interface Recognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  onresult: ((event: RecognitionEvent) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
}

export type RecognitionSource = () => Recognition | null

interface RecognitionWindow {
  SpeechRecognition?: new () => Recognition
  webkitSpeechRecognition?: new () => Recognition
}

/** The browser's listener, or nothing where there is none — Firefox, mainly. */
export function browserRecognition(): Recognition | null {
  const source = window as unknown as RecognitionWindow
  const Constructor = source.SpeechRecognition ?? source.webkitSpeechRecognition
  return Constructor === undefined ? null : new Constructor()
}

/**
 * Everything heard in this session, settled words and the ones still being
 * revised together.
 *
 * A result is final or not, and an unsettled one is replaced by the next
 * event rather than added to. Reading from `resultIndex` alone would lose
 * words: a browser is free to re-send earlier results, and Chrome does.
 */
export function transcriptOf(event: RecognitionEvent): string {
  let text = ""
  for (let index = 0; index < event.results.length; index += 1) {
    const result = event.results[index]
    if (result !== undefined) text += result[0]?.transcript ?? ""
  }
  return text
}

export interface Dictation {
  /** Whether this browser can listen at all. */
  supported: boolean
  listening: Ref<boolean>
  /**
   * Why the last session ended badly, in the browser's own word, until the
   * microphone that shows it has said so. Silence is not a failure: a pause
   * long enough to end the session is how dictation normally finishes.
   */
  failure: Ref<string>
  /** Forget the reason, once it has been said. */
  dismissFailure: () => void
  /** Listen, or stop listening if it already is. */
  toggle: () => void
  stop: () => void
}

/**
 * One listener for the life of whoever speaks into it.
 *
 * `write` is given everything heard since listening began, every time it
 * changes, so the caller can keep it beside whatever was already typed or
 * written rather than working out what is new.
 */
export function useDictation(
  write: (heard: string) => void,
  create: RecognitionSource = browserRecognition
): Dictation {
  const engine = create()
  const listening = ref(false)
  const failure = ref("")

  if (engine !== null) {
    engine.continuous = true
    engine.interimResults = true
    // The browser's own language, which is the one its owner speaks to it in.
    engine.lang = navigator.language
    engine.onresult = (event) => {
      const heard = transcriptOf(event)
      if (heard !== "") write(heard)
    }
    engine.onend = () => { listening.value = false }
    engine.onerror = (event) => {
      listening.value = false
      if (event.error !== "no-speech" && event.error !== "aborted") failure.value = event.error
    }
  }

  function stop() {
    if (engine === null || !listening.value) return
    listening.value = false
    engine.stop()
  }

  function toggle() {
    if (engine === null) return
    if (listening.value) { stop(); return }
    listening.value = true
    try { engine.start() }
    catch { listening.value = false }
  }

  function dismissFailure() {
    failure.value = ""
  }

  return { supported: engine !== null, listening, failure, dismissFailure, toggle, stop }
}

/** Where words being dictated stand in a text somebody may also change. */
export interface SpeechPlace {
  from: number
  to: number
}

/** One answer from the recogniser, as a change to the text it falls in. */
export interface SpeechEdit {
  from: number
  to: number
  text: string
}

function inside(index: number, length: number): number {
  return Math.min(Math.max(index, 0), length)
}

/**
 * The words of one dictation session, and where they stand.
 *
 * The recogniser answers with everything heard so far, settled words and the
 * ones still being revised together, so a revision replaces what was written
 * before rather than adding to it. The characters are not held here — the
 * editor or the field owns them — only the place they stand in and what of the
 * session is already down, because somebody may keep typing beside them.
 */
export class SpeechWriter {
  private place: SpeechPlace | null = null
  /** What of the session already stands before this place. */
  private spoken = ""
  /** Everything heard when the place was last written, lost ones included. */
  private heard = ""

  /** Words go where the caret is, and a selection gives way to them. */
  begin(caret: SpeechPlace) {
    this.place = { from: caret.from, to: caret.to }
    this.spoken = ""
    this.heard = ""
  }

  /**
   * Somebody typed or pasted: the place is gone, and what is heard next goes
   * where they left the caret rather than over their work. What is already
   * down before it is remembered, so no word is written twice.
   */
  interrupt() {
    if (this.place === null) return
    this.place = null
    this.spoken = this.heard
  }

  /**
   * What one answer does: everything heard so far replaces the words it
   * revises. `length` is the text's own, which a revision may have outgrown.
   */
  write(length: number, caret: number, heard: string): SpeechEdit {
    const start = this.place ?? { from: caret, to: caret }
    const from = inside(start.from, length)
    const to = Math.max(from, inside(start.to, length))
    const text = heard.startsWith(this.spoken) ? heard.slice(this.spoken.length) : heard
    this.place = { from, to: from + text.length }
    this.heard = heard
    return { from, to, text }
  }
}
