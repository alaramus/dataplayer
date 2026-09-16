import { computed } from "vue"
import type { ComputedRef } from "vue"

import type { ConversationSummary } from "@/client"
import type { AttentionItem } from "@/shared/notifications"
import { useSpaceStore } from "@/stores/space"

import { useAiConversations } from "./api"
import { requestAiConversation } from "./state"

/**
 * A chat where the agent stopped mid-answer and waits for a person (D113).
 *
 * Not dismissible: the question is still unanswered, so the row is a state,
 * not news, and it goes by itself once the answer is given or the run stopped.
 */

export function waitingItem(
  chat: ConversationSummary,
  open: (conversationId: string) => void
): AttentionItem {
  return {
    id: `ai-waiting:${chat.id}`,
    tone: "warning",
    title: `The agent waits in “${chat.title}”`,
    detail: "It cannot continue until its question there is answered.",
    at: Date.parse(chat.updated_at ?? "") || Date.now(),
    action: { label: "Answer", run: () => { open(chat.id) } },
    dismiss: null,
  }
}

export function useAiAttention(): ComputedRef<AttentionItem[]> {
  const list = useAiConversations()
  const space = useSpaceStore()
  return computed(() => (list.data.value?.data ?? [])
    .filter((chat) => chat.waiting)
    .map((chat) => waitingItem(chat, (id) => {
      space.show("ai")
      requestAiConversation(id)
    })))
}
