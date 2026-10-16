import type { ConversationSummary, QuickChatSummary } from "@/client"
import { t } from "@/shared/i18n"

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
export function chatStateWords(state: ChatState): string | null {
  return state === "idle" ? null : t(`ai.state.${state}`)
}
