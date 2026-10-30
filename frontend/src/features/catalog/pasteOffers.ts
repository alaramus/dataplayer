/**
 * Paste of a clipboard from another connection, as plain decisions (D164).
 *
 * The server says what the clipboard can become here; these functions only
 * choose between its answers, so no kind of paste is named on this side.
 */

import type { ClipboardOffer, PasteOffer } from "@/client"
import type { ClipboardMode } from "@/features/catalog/clipboard"
import { t } from "@/shared/i18n"

/**
 * What a Paste was chosen with.
 *
 * Kept while its windows are open, because the catalog moves on while the
 * person decides, and the paste must not follow it (D162).
 */
export interface CrossPasteIntent {
  sourceConnectorId: string
  sourceNodeIds: string[]
  sourceLabel: string
  mode: ClipboardMode
  destinationConnectorId: string
  destinationNodeId: string | null
  destinationLabel: string
  /** The one node ticked at the destination, which some offers act on (D166). */
  targetNodeId: string | null
  targetLabel: string
  /** Every usable offer; more than one opens a list to choose from. */
  offers: PasteOffer[]
}

/** The offers Paste can run: available, or held back only by a taken name. */
export function usableOffers(offers: PasteOffer[]): PasteOffer[] {
  return offers.filter((offer) => offer.available || offer.name_conflict === true)
}

/**
 * What the menu's Paste runs, and what it leaves to a line of its own.
 *
 * Adding rows goes into the table ticked here rather than into the place, so it
 * is a command of its own that the tick turns on. Paste opens the one window
 * that fits what was copied: the server has already let a better fit stand in
 * for the rest (D182).
 */
export function pasteLines(offers: PasteOffer[]): { paste: PasteOffer[]; into: PasteOffer | null } {
  return {
    paste: offers.filter((offer) => offer.workflow !== "into-relation"),
    into: offers.find((offer) => offer.workflow === "into-relation") ?? null,
  }
}

/**
 * Why Paste is off here, or nothing when it is on.
 *
 * How many places the catalog stands in is not asked here: a kind that needs
 * one says so as its reason, and a copy of tables chooses its own (D182).
 */
export function pasteHint(state: {
  checking: boolean
  failed: boolean
  offers: PasteOffer[] | undefined
}): string | undefined {
  if (state.checking) return t("catalog.paste.checking")
  if (state.failed) return t("catalog.paste.check_failed")
  const offers = state.offers ?? []
  if (usableOffers(offers).length > 0) return undefined
  return offers.find((offer) => offer.reason)?.reason ?? t("catalog.paste.nothing_takes")
}

export type PasteStep =
  | "run"
  | "conflict"
  | "file-name"
  | "new-relation"
  | "into-relation"
  | "copy-tables"

/** Which window a chosen offer opens first; `run` opens none. */
export function firstStep(offer: PasteOffer): PasteStep {
  const workflow = offer.workflow ?? "run"
  if (workflow !== "run") return workflow
  return offer.name_conflict === true ? "conflict" : "run"
}

/** Where an offer acts, in the words the catalog shows it by. */
export function offerPlace(offer: PasteOffer, intent: CrossPasteIntent): string {
  return offer.workflow === "into-relation" ? intent.targetLabel : intent.destinationLabel
}

export interface HoldLine {
  enabled: boolean
  reason?: string
}

/**
 * Whether Copy and Cut are drawn and usable for what is ticked.
 *
 * A source with its own Paste (D74) holds anything it lists. Any other asks
 * the server whether something elsewhere could take the selection; absent
 * from that answer means nothing could, and the line is not drawn.
 */
export function holdLines(
  ownPaste: boolean,
  ticked: number,
  offer: ClipboardOffer | undefined
): { copy?: HoldLine; cut?: HoldLine } {
  // Whether there is something to hold is the ticks' answer. Whether this
  // source holds a selection at all is its Paste, or its offer for none;
  // what is held is judged when it is pasted.
  const line = ticked === 0
    ? { enabled: false, reason: t("catalog.actions.no_target.node") }
    : { enabled: true }
  if (ownPaste) return { copy: line, cut: line }
  return {
    ...(offer?.can_copy ? { copy: line } : {}),
    ...(offer?.can_cut ? { cut: line } : {}),
  }
}
