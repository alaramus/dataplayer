import { ref, watch } from "vue"
import type { Ref } from "vue"

/** Unsent text survives chat and space switches in this browser page. */
const drafts = new Map<string, string>()

export function hasAiDraft(conversationId: string): boolean {
  return Boolean(drafts.get(conversationId))
}

export function useAiDraft(conversationId: string): Ref<string> {
  const draft = ref(drafts.get(conversationId) ?? "")
  watch(draft, (text) => {
    if (text) drafts.set(conversationId, text)
    else drafts.delete(conversationId)
  }, { flush: "sync" })
  return draft
}

/** Text put in a composer before it is mounted: the search's words (S10). */
export function setAiDraft(conversationId: string, text: string): void {
  if (text) drafts.set(conversationId, text)
  else drafts.delete(conversationId)
}
