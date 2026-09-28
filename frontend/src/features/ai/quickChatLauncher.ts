import { ref } from "vue"

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

/**
 * The question asked about a selection: the ask, then the selection quoted.
 * The selection is not repeated on the first line — a short one read twice —
 * so the chat is named by `explainTitle` rather than by that line.
 */
export function explainRequest(text: string): string {
  return `Explain in more detail:\n\n${quoteSelection(text)}`
}

const TITLE_CHARS = 60

/** What a chat opened on a selection is called in the history: the selection. */
export function explainTitle(text: string): string {
  const line = text.trim().replace(/\s+/g, " ")
  return line.length > TITLE_CHARS ? `${line.slice(0, TITLE_CHARS - 1).trimEnd()}…` : line
}

export function quoteSelection(text: string): string {
  return text.trim().slice(0, 8000).split("\n").map((line) => `> ${line}`).join("\n")
}
