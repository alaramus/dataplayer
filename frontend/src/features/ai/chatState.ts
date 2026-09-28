import type { ConversationSummary, QuickChatSummary } from "@/client"

/** What the dot beside a chat in the history says. */
export type ChatState = "idle" | "working" | "waiting" | "failed"

/**
 * Read off the flags the server derives from the chat's newest run. Waiting
 * comes first because a paused run is also an active one. A quick chat has
 * no run the server owns, so it is always idle.
 */
export function chatStateOf(chat: ConversationSummary | QuickChatSummary): ChatState {
  if (!("active" in chat)) return "idle"
  if (chat.waiting) return "waiting"
  if (chat.active) return "working"
  if (chat.failed === true) return "failed"
  return "idle"
}

/** The words for a state, shown with the chat's name on hover. */
export const CHAT_STATE_WORDS: Record<ChatState, string | null> = {
  idle: null,
  working: "The agent is working",
  waiting: "The agent waits for your answer",
  failed: "The last answer failed",
}
