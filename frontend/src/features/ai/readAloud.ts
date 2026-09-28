import { ref } from "vue"

import { plainSpeechText } from "./streaming"

/**
 * Reading a message aloud. One voice for the whole browser, so one state for
 * every chat: a second message started in another window stops the first,
 * and the first one's button must stop saying "stop".
 *
 * The message content is the key: the engine reports the end on the
 * utterance, and a fresh read of the same text restarts it.
 */
const speaking = ref<string | null>(null)

export function useReadAloud() {
  function stop() {
    window.speechSynthesis.cancel()
    speaking.value = null
  }

  function listen(text: string) {
    if (speaking.value === text) {
      stop()
      return
    }
    window.speechSynthesis.cancel()
    const plain = plainSpeechText(text)
    if (!plain) return
    const utterance = new SpeechSynthesisUtterance(plain)
    utterance.onend = () => { if (speaking.value === text) speaking.value = null }
    utterance.onerror = () => { if (speaking.value === text) speaking.value = null }
    speaking.value = text
    window.speechSynthesis.speak(utterance)
  }

  return { speaking, listen, stop }
}
