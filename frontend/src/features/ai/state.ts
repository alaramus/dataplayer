import { ref } from "vue"

import { serverStorageKey } from "@/shared/servers/context"

const CONVERSATION_KEY = "dataplayer-ai-conversation"

export function aiConversationStorageKey(): string { return serverStorageKey(CONVERSATION_KEY) }
export function rememberAiConversation(id: string | null, storage: Storage = localStorage): void {
  try {
    if (id) storage.setItem(aiConversationStorageKey(), id)
    else storage.removeItem(aiConversationStorageKey())
  } catch { /* Selection remains in memory. */ }
}
export function rememberedAiConversation(storage: Storage = localStorage): string | null {
  try { return storage.getItem(aiConversationStorageKey()) } catch { return null }
}

/**
 * A chat somebody outside the space — the Needs-you sheet — wants open (D113).
 *
 * A module-level ref rather than a prop chain: the sheet and the space meet
 * only here, and the space clears the request once it has honoured it.
 */
export const requestedAiConversation = ref<string | null>(null)
export function requestAiConversation(id: string): void { requestedAiConversation.value = id }
