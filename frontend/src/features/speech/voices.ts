import { onBeforeUnmount, ref } from "vue"

/**
 * The voices of this browser's speech synthesis.
 *
 * Read here and nowhere else: the list arrives after the page — Chrome's
 * first read is usually empty — so it is watched through `voiceschanged`
 * rather than taken once. Where there is no synthesis at all there are no
 * voices either; dictation's recogniser is the same kind of absence.
 */
export function speechSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.speechSynthesis === "object" &&
    typeof window.speechSynthesis.getVoices === "function"
  )
}

/** A voice as the choice names it: who it is, and which language it reads. */
export function voiceLabel(voice: Pick<SpeechSynthesisVoice, "name" | "lang">): string {
  return voice.lang ? `${voice.name} · ${voice.lang}` : voice.name
}

function current(): SpeechSynthesisVoice[] {
  if (!speechSupported()) return []
  try {
    return [...window.speechSynthesis.getVoices()]
  } catch {
    return []
  }
}

export function useVoices() {
  const voices = ref<SpeechSynthesisVoice[]>(current())
  const supported = speechSupported()

  function refresh() {
    voices.value = current()
  }

  if (supported) {
    window.speechSynthesis.addEventListener("voiceschanged", refresh)
    onBeforeUnmount(() => {
      window.speechSynthesis.removeEventListener("voiceschanged", refresh)
    })
  }

  return { voices, supported }
}
