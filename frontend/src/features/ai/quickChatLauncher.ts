import { ref } from "vue"

import type { QuickChatSummary } from "@/client"

export type QuickChatIntent =
  | { kind: "open" }
  | { kind: "chat"; id: string }
  | { kind: "explain"; text: string }

// An entry point any application space can use without owning the window.
export const quickChatIntent = ref<{ id: number; request: QuickChatIntent } | null>(null)
export const deletedQuickChat = ref<string | null>(null)
let nextId = 0

export function openQuickChat(request: QuickChatIntent = { kind: "open" }) {
  quickChatIntent.value = { id: ++nextId, request }
}

export function forgetQuickChat(id: string) {
  deletedQuickChat.value = id
}

/** Find an untouched draft anywhere in quick-chat history, as the agent chat does. */
export async function reusableEmptyQuickChat(
  chats: readonly QuickChatSummary[],
  read: (id: string) => Promise<{ messages: readonly unknown[] }>
): Promise<string | null> {
  for (const chat of chats) {
    if (chat.title !== "New quick chat") continue
    const loaded = await read(chat.id)
    if (loaded.messages.length === 0) return chat.id
  }
  return null
}

export function explainRequest(text: string): string {
  const preview = text.trim().replace(/\s+/g, " ").slice(0, 60)
  return `Explain in more detail: ${preview}\n\n${quoteSelection(text)}`
}

export function quoteSelection(text: string): string {
  return text.trim().slice(0, 8000).split("\n").map((line) => `> ${line}`).join("\n")
}
