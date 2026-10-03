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
 * A chat somebody outside the space — the Needs-you sheet, the search — wants
 * open (D113, D205).
 *
 * A module-level ref rather than a prop chain: the sheet and the space meet
 * only here, and the space clears the request once it has honoured it. Set
 * before the space has ever been shown, it is waiting there when it mounts.
 */
export const requestedAiConversation = ref<string | null>(null)
export function requestAiConversation(id: string): void { requestedAiConversation.value = id }

/** A project the search found, to be unfolded and brought into view in the history. */
export const requestedAiProject = ref<string | null>(null)
export function requestAiProject(id: string): void { requestedAiProject.value = id }

/**
 * Words the search hands to a new chat, put in its composer unsent (S10).
 * Honoured and cleared by the space, like the requests above.
 */
export const requestedAiDraft = ref<string | null>(null)
export function askTheAgent(words: string): void { requestedAiDraft.value = words }
