import { ref } from "vue"

import { useVoiceStore } from "@/stores/voice"

import { plainSpeechText } from "./speechText"
import { availableVoices } from "./voices"

/**
 * Reading text aloud. One voice for the whole browser, so one state for
 * every reader: a second text started anywhere stops the first, and the
 * first one's button must stop saying "stop".
 *
 * Whoever started the reading is the key, not the text: a file edited while
 * it is read is still the one being read, and two panels showing the same
 * text are two readers. Plain sources read as they are; Markdown loses its
 * marks only when the caller says the text is Markdown.
 */
const speaking = ref<unknown>(null)

export function useReadAloud() {
  function stop() {
    window.speechSynthesis.cancel()
    speaking.value = null
  }

  function listen(reader: unknown, text: string, options?: { stripMarkdown?: boolean }) {
    if (speaking.value === reader) {
      stop()
      return
    }
    window.speechSynthesis.cancel()
    const plain = options?.stripMarkdown === true ? plainSpeechText(text) : text.trim()
    if (!plain) return
    const utterance = new SpeechSynthesisUtterance(plain)
    // The chosen voice, or the browser default when there is none or it is
    // gone: a voice stored on another machine names nothing here.
    const wanted = useVoiceStore().voice
    const voice = wanted ? availableVoices().find((one) => one.voiceURI === wanted) : undefined
    if (voice) utterance.voice = voice
    utterance.onend = () => { if (speaking.value === reader) speaking.value = null }
    utterance.onerror = () => { if (speaking.value === reader) speaking.value = null }
    speaking.value = reader
    window.speechSynthesis.speak(utterance)
  }

  return { speaking, listen, stop }
}
