import { serverStorageKey } from "@/shared/servers/context"

const CONVERSATION_KEY = "dataplayer-ai-conversation"

export function aiConversationStorageKey(): string { return serverStorageKey(CONVERSATION_KEY) }
export function rememberAiConversation(id: string | null, storage: Storage = localStorage): void {
  try { id ? storage.setItem(aiConversationStorageKey(), id) : storage.removeItem(aiConversationStorageKey()) } catch { /* Selection remains in memory. */ }
}
export function rememberedAiConversation(storage: Storage = localStorage): string | null {
  try { return storage.getItem(aiConversationStorageKey()) } catch { return null }
}
