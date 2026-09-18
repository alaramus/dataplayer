import { ref } from "vue"
import type { Ref } from "vue"

/**
 * Speaking a message instead of typing it, through the browser's own listener.
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
  /** Listen, or stop listening if it already is. */
  toggle: () => void
  stop: () => void
}

/**
 * One listener for the life of the composer.
 *
 * `write` is given everything heard since listening began, every time it
 * changes, so the caller can keep it beside whatever was already typed rather
 * than working out what is new.
 */
export function useDictation(
  write: (heard: string) => void,
  fail: (reason: string) => void,
  create: RecognitionSource = browserRecognition
): Dictation {
  const engine = create()
  const listening = ref(false)

  if (engine !== null) {
    engine.continuous = true
    engine.interimResults = true
    // The browser's own language, which is the one its owner speaks to it in.
    engine.lang = navigator.language
    engine.onresult = (event) => { write(transcriptOf(event)) }
    engine.onend = () => { listening.value = false }
    engine.onerror = (event) => {
      listening.value = false
      // Silence is not a failure: a pause long enough to end the session is
      // how dictation normally finishes, and saying so would be noise.
      if (event.error !== "no-speech" && event.error !== "aborted") fail(event.error)
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

  return { supported: engine !== null, listening, toggle, stop }
}
