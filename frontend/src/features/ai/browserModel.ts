import { ref } from "vue"

import type { QuickTurnMessage } from "@/client"
import { serverStorageKey } from "@/shared/servers/context"
import type { SelectOption } from "@/shared/ui"
import { t } from "@/shared/i18n"

/**
 * Gemini Nano, which Chrome runs on the person's own machine, for the quick
 * chat only (D223). The server never calls it: it keeps the question, hands
 * back the history, and stores what was written here.
 */
export const BROWSER_MODEL_KEY = "browser:gemini-nano"
export const BROWSER_MODEL_LABEL = "Gemini Nano"

/** `unsupported` is a browser without the Prompt API; the rest are Chrome's own words. */
export type BrowserModelState = "unsupported" | "unavailable" | "downloadable" | "downloading" | "available"

type Role = "system" | "user" | "assistant"
interface PromptMessage { role: Role; content: string }
interface PromptSession {
  promptStreaming(input: string, options?: { signal?: AbortSignal }): AsyncIterable<string>
  destroy(): void
}
interface DownloadMonitor {
  addEventListener(type: "downloadprogress", listener: (event: { loaded: number }) => void): void
}
interface PromptFactory {
  availability(): Promise<Exclude<BrowserModelState, "unsupported">>
  create(options?: { initialPrompts?: PromptMessage[]; monitor?: (monitor: DownloadMonitor) => void }): Promise<PromptSession>
}

// Declared here rather than globally: one browser has it, and only this file reads it.
function factory(): PromptFactory | undefined {
  return (globalThis as { LanguageModel?: PromptFactory }).LanguageModel
}

export async function readBrowserModelState(): Promise<BrowserModelState> {
  const found = factory()
  if (!found) return "unsupported"
  try { return await found.availability() } catch { return "unavailable" }
}

/** What the list says of the row, and whether it can be chosen. */
export function browserModelOptions(state: BrowserModelState | null): SelectOption[] {
  return [
    { label: t("ai.browser.heading"), value: "browser:heading", group: true, separator: true },
    {
      label: BROWSER_MODEL_LABEL,
      value: BROWSER_MODEL_KEY,
      separator: true,
      description: state === null ? undefined : t(`ai.browser.${state}`),
      disable: state === "unsupported" || state === "unavailable",
    },
  ]
}

const state = ref<BrowserModelState | null>(null)
/** A fraction while Chrome downloads, null when it has not said how far. */
const progress = ref<number | null>(null)
const downloading = ref(false)

/** One state for every window: Chrome holds one model, whoever asked. */
export function useBrowserModel() {
  async function refresh(): Promise<void> { state.value = await readBrowserModelState() }
  /** Must run from a press: Chrome refuses to start the download without one. */
  async function download(): Promise<void> {
    const found = factory()
    if (!found || downloading.value) return
    downloading.value = true
    progress.value = null
    state.value = "downloading"
    try {
      const session = await found.create({
        monitor: (monitor) => monitor.addEventListener("downloadprogress", (event) => { progress.value = event.loaded }),
      })
      session.destroy()
    } finally {
      downloading.value = false
      await refresh()
    }
  }
  return { state, progress, downloading, refresh, download }
}

/**
 * The older half of the turns dropped, the instructions kept. Nano's window is
 * a few thousand tokens, so a history the server found short enough for a
 * provider may still not fit.
 */
export function shorterHistory(messages: readonly PromptMessage[]): PromptMessage[] {
  const system = messages.filter((one) => one.role === "system")
  const turns = messages.filter((one) => one.role !== "system")
  return [...system, ...turns.slice(Math.ceil(turns.length / 2))]
}

/** The answer, streamed to `onText` as it is written; `signal` stops it. */
export async function answerInBrowser(turn: {
  prompt: string
  history: readonly QuickTurnMessage[]
  question: string
  onText: (text: string) => void
  signal?: AbortSignal
}): Promise<string> {
  const found = factory()
  if (!found) throw new Error(t("ai.browser.cannot_run"))
  turn.signal?.throwIfAborted()
  let initial: PromptMessage[] = [{ role: "system", content: turn.prompt }, ...turn.history]
  let session: PromptSession
  for (;;) {
    try {
      session = await found.create({ initialPrompts: initial })
      break
    } catch (cause) {
      const shorter = shorterHistory(initial)
      if (shorter.length === initial.length) throw cause
      initial = shorter
    }
  }
  let written = ""
  try {
    for await (const piece of session.promptStreaming(turn.question, { signal: turn.signal })) {
      written += piece
      turn.onText(piece)
    }
  } finally {
    session.destroy()
  }
  return written
}

const CHOSEN_KEY = "dataplayer-ai-quick-browser-model"

/**
 * Whether the quick chat was last left on the browser's model. Kept here, not
 * in the settings: the settings name a model the server can call.
 */
export function rememberBrowserModel(chosen: boolean, storage: Storage = localStorage): void {
  try {
    if (chosen) storage.setItem(serverStorageKey(CHOSEN_KEY), "true")
    else storage.removeItem(serverStorageKey(CHOSEN_KEY))
  } catch { /* The choice holds for this page only. */ }
}
export function browserModelRemembered(storage: Storage = localStorage): boolean {
  try { return storage.getItem(serverStorageKey(CHOSEN_KEY)) === "true" } catch { return false }
}
