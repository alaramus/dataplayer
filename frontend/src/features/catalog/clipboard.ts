/**
 * What the catalog is holding, waiting to be put somewhere else.
 *
 * Copy and Cut change nothing: they remember a selection and a verb, and the
 * move itself is one action of the source — the client never learns what
 * copying a file means. Module-level rather than a store: one small piece of
 * state with one reader, and Pinia is for what one screen shares with another.
 */

import { computed, ref } from "vue"

export type ClipboardMode = "copy" | "move"

export interface Clipboard {
  /** The connection the nodes belong to. Nothing crosses connections. */
  connectorId: string
  nodeIds: string[]
  mode: ClipboardMode
}

const held = ref<Clipboard | null>(null)

/** What is held, or nothing. Read-only: it is changed through the two verbs. */
export const clipboard = computed(() => held.value)

export function holdNodes(
  connectorId: string,
  nodeIds: string[],
  mode: ClipboardMode
): void {
  if (nodeIds.length === 0) return
  held.value = { connectorId, nodeIds: [...nodeIds], mode }
}

export function forgetClipboard(): void {
  held.value = null
}

/**
 * What is held for this connection, or nothing.
 *
 * A selection belongs to the connection it came from: an opaque node id means
 * nothing to another source, and the two roots have nothing to do with each
 * other. Asked rather than assumed, so a second connection opened beside the
 * first does not offer to paste what is not its own.
 */
export function heldFor(connectorId: string | null): Clipboard | null {
  const current = held.value
  if (current === null || connectorId === null) return null
  return current.connectorId === connectorId ? current : null
}

/**
 * What is held, said in one phrase.
 *
 * The count rather than the names: the names are on screen in the catalog the
 * selection came from, and a bar is not the place to list five of them.
 */
export function clipboardWording(current: Clipboard): string {
  const what =
    current.nodeIds.length === 1 ? "1 item" : `${String(current.nodeIds.length)} items`
  return current.mode === "copy" ? `${what} to copy` : `${what} to move`
}
