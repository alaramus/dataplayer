import type { ConversationSummary } from "@/client"

/** A draft is reusable only while nobody has started or sent anything in it. */
export async function reusableEmptyChat(
  chats: readonly ConversationSummary[],
  read: (id: string) => Promise<{ messages: readonly unknown[]; runs: readonly unknown[] }>
): Promise<string | null> {
  for (const chat of chats) {
    if (chat.title !== "New chat" || chat.active || chat.waiting) continue
    const conversation = await read(chat.id)
    if (conversation.messages.length === 0 && conversation.runs.length === 0) return chat.id
  }
  return null
}
