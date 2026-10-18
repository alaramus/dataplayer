import type { AgentRunPublic, ConversationMessagePublic } from "@/client"

/**
 * The runs that ended without an answer to show the ending under: they get a
 * banner of their own. Only an answer stands for its run — the question
 * carries the run's id too, and counting it hid every run that failed before
 * a word of the answer, leaving the chat with nothing but a red mark in the
 * list.
 */
export function unansweredEnds(
  messages: readonly Pick<ConversationMessagePublic, "role" | "run_id">[],
  runs: readonly AgentRunPublic[]
): AgentRunPublic[] {
  const answered = new Set(messages.flatMap((message) =>
    message.role === "assistant" && message.run_id ? [message.run_id] : []))
  return runs.filter((run) => !answered.has(run.id) && !["running", "awaiting_answer", "succeeded"].includes(run.status))
}
