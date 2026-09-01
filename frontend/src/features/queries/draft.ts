import type { QueryDocumentPublic, QueryDocumentUpdate } from "@/client"

/**
 * What the editor holds that the server has not accepted yet, and what it does
 * when the two disagree.
 *
 * Plain functions so the rules can be tested without mounting an editor: what
 * a save carries, what a conflict offers, and what may be kept in this browser
 * tab while the server cannot be reached (D63).
 */

/** What a document is at this moment, said in one word to the person editing. */
export type SaveState = "saved" | "dirty" | "saving" | "conflict" | "unsynchronised"

/** The parts of a document a person edits, including how it is laid out. */
export interface DraftState {
  body: string
  title: string | null
  wrap: boolean
  /** Where the line between the editor and the results sits (D65). */
  split: number
}

/** Whether lines wrap, with the default the server would have applied. */
function wrapOf(document: QueryDocumentPublic): boolean {
  return document.layout.wrap === true
}

function splitOf(document: QueryDocumentPublic): number {
  return document.layout.split_ratio ?? 0.6
}

export function draftOf(document: QueryDocumentPublic): DraftState {
  return {
    body: document.body,
    title: document.title,
    wrap: wrapOf(document),
    split: splitOf(document),
  }
}

export function changed(document: QueryDocumentPublic, draft: DraftState): boolean {
  return (
    draft.body !== document.body ||
    draft.title !== document.title ||
    draft.wrap !== wrapOf(document) ||
    draft.split !== splitOf(document)
  )
}

/**
 * The save to send, carrying only what actually differs.
 *
 * Absent is not null on the way to the server, so a body that has not been
 * touched is not restated and a title cleared on purpose still travels. Null
 * when nothing differs: there is nothing to save, and an autosave that writes
 * anyway would spend a revision on every keystroke pause.
 */
export function saveFor(
  document: QueryDocumentPublic,
  draft: DraftState
): QueryDocumentUpdate | null {
  if (!changed(document, draft)) return null
  return {
    revision: document.revision,
    ...(draft.body === document.body ? {} : { body: draft.body }),
    ...(draft.title === document.title ? {} : { title: draft.title }),
    ...(draft.wrap === wrapOf(document) && draft.split === splitOf(document)
      ? {}
      : { layout: { ...document.layout, wrap: draft.wrap, split_ratio: draft.split } }),
  }
}

/** The three answers to "this changed elsewhere", and no fourth (D63). */
export type ConflictChoice = "keep-mine" | "use-remote" | "save-a-copy"

/**
 * What keeping your own text means once the remote revision is known.
 *
 * The same text, sent again on top of what is there now. Deliberate: the
 * person was shown both and said which one survives.
 */
export function keepMine(remote: QueryDocumentPublic, draft: DraftState): QueryDocumentUpdate {
  return {
    revision: remote.revision,
    body: draft.body,
    title: draft.title,
    layout: { ...remote.layout, wrap: draft.wrap, split_ratio: draft.split },
  }
}

/**
 * What a copy is called.
 *
 * A draft has no name to build on, so it gets one that says where it came
 * from rather than nothing at all.
 */
export function copyTitle(title: string | null): string {
  return title === null ? "Unsaved copy" : `${title} (copy)`
}

/** One tab's unsynchronised text, kept only while the server cannot be reached. */
export interface DocumentShadow {
  documentId: string
  revision: number
  body: string
  title: string | null
}

const SHADOW_PREFIX = "dp.query.shadow."

/**
 * `sessionStorage` and not `localStorage`, and one key per document.
 *
 * D63 allows exactly one unsynchronised shadow, in the tab that holds the
 * unsaved text, removed once a save succeeds. Session storage is what makes
 * that true without a rule anybody has to keep: it dies with the tab, so this
 * never becomes a durable plaintext library of everybody's SQL.
 */
export function readShadow(documentId: string): DocumentShadow | null {
  try {
    const raw = sessionStorage.getItem(SHADOW_PREFIX + documentId)
    if (raw === null) return null
    const parsed: unknown = JSON.parse(raw)
    if (parsed === null || typeof parsed !== "object") return null
    const shadow = parsed as Partial<DocumentShadow>
    if (typeof shadow.body !== "string" || typeof shadow.revision !== "number") return null
    return {
      documentId,
      revision: shadow.revision,
      body: shadow.body,
      title: typeof shadow.title === "string" ? shadow.title : null,
    }
  } catch {
    return null
  }
}

export function writeShadow(shadow: DocumentShadow): void {
  try {
    sessionStorage.setItem(SHADOW_PREFIX + shadow.documentId, JSON.stringify(shadow))
  } catch {
    // A tab with no storage left keeps its text on screen and says it is
    // unsynchronised; losing the shadow is not worth interrupting typing for.
  }
}

export function clearShadow(documentId: string): void {
  try {
    sessionStorage.removeItem(SHADOW_PREFIX + documentId)
  } catch {
    // Nothing to do: the shadow is a convenience, not a record.
  }
}

/**
 * Whether a shadow found on reload is worth putting back.
 *
 * Only text the server has not got: a shadow of an older revision was written
 * before somebody else's save landed, and offering it as "your unsaved work"
 * would be a lie about which of the two is newer.
 */
export function recoverable(
  shadow: DocumentShadow | null,
  document: QueryDocumentPublic
): boolean {
  if (shadow === null) return false
  if (shadow.revision !== document.revision) return false
  return shadow.body !== document.body || shadow.title !== document.title
}
