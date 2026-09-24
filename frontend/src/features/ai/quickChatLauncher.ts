import { ref } from "vue"

export type QuickChatIntent =
  | { kind: "open" }
  | { kind: "explain"; text: string }

// An entry point any application space can use without owning the window.
export const quickChatIntent = ref<{ id: number; request: QuickChatIntent } | null>(null)
let nextId = 0

export function openQuickChat(request: QuickChatIntent = { kind: "open" }) {
  quickChatIntent.value = { id: ++nextId, request }
}

export function explainRequest(text: string): string {
  const preview = text.trim().replace(/\s+/g, " ").slice(0, 60)
  return `Explain in more detail: ${preview}\n\n${quoteSelection(text)}`
}

export function quoteSelection(text: string): string {
  return text.trim().slice(0, 8000).split("\n").map((line) => `> ${line}`).join("\n")
}
