import { defineStore } from "pinia"
import { ref } from "vue"

export const VOICE_KEY = "dataplayer-voice"

/**
 * The speech voice reading aloud, by its voiceURI; "" is the browser default.
 *
 * Pinia, because the server knows nothing about it (D6): voices live in this
 * browser, so the choice is kept here too. One store serves Preferences, AI
 * settings and every future reader, so a choice in one place is the choice
 * everywhere.
 */
export const useVoiceStore = defineStore("voice", () => {
  const voice = ref<string>(stored())

  function setVoice(value: string) {
    voice.value = value
    try {
      if (value) localStorage.setItem(VOICE_KEY, value)
      else localStorage.removeItem(VOICE_KEY)
    } catch {
      // Keep this session usable when browser storage is full or blocked.
    }
  }

  return { voice, setVoice }
})

function stored(): string {
  try {
    return localStorage.getItem(VOICE_KEY) ?? ""
  } catch {
    // Unavailable or blocked storage is the same as never having been told.
    return ""
  }
}
