import { ref } from "vue"

import { useVoiceStore } from "@/stores/voice"

import { plainSpeechText } from "./speechText"

/**
 * Reading text aloud. One voice for the whole browser, so one state for
 * every reader: a second text started anywhere stops the first, and the
 * first one's button must stop saying "stop".
 *
 * The source text is the key: the engine reports the end on the utterance,
 * and a fresh read of the same text restarts it. Markdown is stripped to
 * prose; plain sources read as they are.
 */
const speaking = ref<string | null>(null)

export function useReadAloud() {
  function stop() {
    window.speechSynthesis.cancel()
    speaking.value = null
  }

  function listen(text: string, options?: { stripMarkdown?: boolean }) {
    if (speaking.value === text) {
      stop()
      return
    }
    window.speechSynthesis.cancel()
    const plain = options?.stripMarkdown === false ? text.trim() : plainSpeechText(text)
    if (!plain) return
    const utterance = new SpeechSynthesisUtterance(plain)
    // The chosen voice, or the browser default when there is none or it is
    // gone: a voice stored on another machine names nothing here.
    const wanted = useVoiceStore().voice
    const voice = wanted
      ? (window.speechSynthesis.getVoices?.() ?? []).find((one) => one.voiceURI === wanted)
      : undefined
    if (voice) utterance.voice = voice
    utterance.onend = () => { if (speaking.value === text) speaking.value = null }
    utterance.onerror = () => { if (speaking.value === text) speaking.value = null }
    speaking.value = text
    window.speechSynthesis.speak(utterance)
  }

  return { speaking, listen, stop }
}
