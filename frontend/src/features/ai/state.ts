import { serverStorageKey } from "@/shared/servers/context"

const OPEN_KEY = "dataplayer-ai-open"
const CONVERSATION_KEY = "dataplayer-ai-conversation"

export function aiOpenKey(): string { return serverStorageKey(OPEN_KEY) }
export function aiConversationStorageKey(): string { return serverStorageKey(CONVERSATION_KEY) }
export function rememberAiOpen(open: boolean, storage: Storage = localStorage): void {
  try { open ? storage.setItem(aiOpenKey(), "true") : storage.removeItem(aiOpenKey()) } catch { /* The window still works without persistence. */ }
}
export function rememberedAiOpen(storage: Storage = localStorage): boolean {
  try { return storage.getItem(aiOpenKey()) === "true" } catch { return false }
}
export function rememberAiConversation(id: string | null, storage: Storage = localStorage): void {
  try { id ? storage.setItem(aiConversationStorageKey(), id) : storage.removeItem(aiConversationStorageKey()) } catch { /* Selection remains in memory. */ }
}
export function rememberedAiConversation(storage: Storage = localStorage): string | null {
  try { return storage.getItem(aiConversationStorageKey()) } catch { return null }
}
