/**
 * Paste of a clipboard from another connection, as plain decisions (D164).
 *
 * The server says what the clipboard can become here; these functions only
 * choose between its answers, so no kind of paste is named on this side.
 */

import type { ClipboardOffer, PasteOffer } from "@/client"
import type { ClipboardMode } from "@/features/catalog/clipboard"

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
  offer: PasteOffer
}

/** The offers Paste can run: available, or held back only by a taken name. */
export function usableOffers(offers: PasteOffer[]): PasteOffer[] {
  return offers.filter((offer) => offer.available || offer.name_conflict === true)
}

/** The offer Paste runs, or nothing when there is none. */
export function chosenOffer(offers: PasteOffer[]): PasteOffer | null {
  // Several usable offers would open a list to choose from (D164); no pair
  // has two kinds yet, so the first is the only one.
  return usableOffers(offers)[0] ?? null
}

/** Why Paste is off here, or nothing when it is on. */
export function pasteHint(state: {
  places: number
  checking: boolean
  failed: boolean
  offers: PasteOffer[] | undefined
}): string | undefined {
  if (state.places !== 1) return "Choose one destination folder"
  if (state.checking) return "Checking what can be pasted here"
  if (state.failed) return "Could not check this destination"
  const offers = state.offers ?? []
  if (chosenOffer(offers) !== null) return undefined
  return offers.find((offer) => offer.reason)?.reason ?? "Nothing here can take what was copied"
}

/** Which window a chosen offer opens first, if any. */
export function firstStep(offer: PasteOffer): "name" | "conflict" | "run" {
  // A conversion is never run straight from the menu.
  if (offer.converts === true || offer.suggested_name != null) return "name"
  if (offer.name_conflict === true) return "conflict"
  return "run"
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
  if (ownPaste) {
    const line = ticked === 0
      ? { enabled: false, reason: "Tick a row to use this" }
      : { enabled: true }
    return { copy: line, cut: line }
  }
  return {
    ...(offer?.can_copy ? { copy: lineOf(offer.can_copy) } : {}),
    ...(offer?.can_cut ? { cut: lineOf(offer.can_cut) } : {}),
  }
}

function lineOf(answer: { available: boolean; reason?: string | null }): HoldLine {
  return answer.available
    ? { enabled: true }
    : { enabled: false, ...(answer.reason ? { reason: answer.reason } : {}) }
}
