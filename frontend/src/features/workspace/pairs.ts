/**
 * Two catalogs of two connections in one window, and the one waiting for its
 * second (D167). Plain decisions, so the gesture is tested without a pointer.
 */

import type { PasteOffer } from "@/client"
import { offerPlace } from "@/features/catalog/pasteOffers"
import type { CrossPasteIntent } from "@/features/catalog/pasteOffers"
import { t } from "@/shared/i18n"

import type { CatalogSide } from "./catalogSides"

/** A catalog that could be one side of a pair. */
export interface PairCandidate {
  panelId: string
  connectorId: string
  title: string
}

/** A pair that is open: the two catalog panels, left and right. */
export interface Pair {
  id: string
  left: PairCandidate
  right: PairCandidate
}

/**
 * What offering a catalog to Pair does now.
 *
 * `hold` makes it the waiting one — also when it replaces another waiting
 * catalog, or is dropped a second time; `complete` opens the pair; `refuse`
 * is a catalog of the waiting connection, which a pair would have nothing to
 * show between.
 */
export type PairDrop =
  | { kind: "hold" }
  | { kind: "complete"; left: PairCandidate; right: PairCandidate }
  | { kind: "refuse"; reason: string }

export function dropOnPair(waiting: PairCandidate | null, carried: PairCandidate): PairDrop {
  if (waiting === null || waiting.panelId === carried.panelId) return { kind: "hold" }
  if (waiting.connectorId === carried.connectorId) {
    return { kind: "refuse", reason: t("workspace.pair.already_waiting") }
  }
  return { kind: "complete", left: waiting, right: carried }
}

/** What a catalog's Pair command says, and whether it is refused. */
export interface PairCommand {
  tooltip: string
  refused: boolean
}

export function pairCommand(waiting: PairCandidate | null, candidate: PairCandidate): PairCommand {
  const drop = dropOnPair(waiting, candidate)
  if (drop.kind === "refuse") {
    return { tooltip: t("workspace.pair.with_another_refused", { reason: drop.reason }), refused: true }
  }
  if (drop.kind === "complete") {
    return { tooltip: t("workspace.pair.with", { name: drop.left.title }), refused: false }
  }
  return { tooltip: t("workspace.pair.with_another"), refused: false }
}

export function pairTitle(pair: Pair): string {
  return t("workspace.pair.title", { left: pair.left.title, right: pair.right.title })
}

export function swapped(pair: Pair): Pair {
  return { ...pair, left: pair.right, right: pair.left }
}

/** Whether a pair still has both its catalogs torn off into it. */
export function pairIntact(pair: Pair, grouped: ReadonlySet<string>): boolean {
  return grouped.has(pair.left.panelId) && grouped.has(pair.right.panelId)
}

/**
 * The Paste an item of the bar runs: the ticks of one side into the place,
 * or the one tick, of the other. The same intent a Paste in that place would
 * make, so the same windows follow (D167).
 */
export function pasteIntentFor(
  offer: PasteOffer,
  source: CatalogSide,
  destination: CatalogSide
): CrossPasteIntent {
  return {
    sourceConnectorId: source.connectorId,
    sourceNodeIds: [...source.ticked],
    sourceLabel: source.tickedLabel,
    mode: offer.mode ?? "copy",
    destinationConnectorId: destination.connectorId,
    destinationNodeId: destination.place,
    destinationLabel: destination.placeLabel,
    targetNodeId: destination.ticked.length === 1 ? destination.ticked[0] ?? null : null,
    targetLabel: destination.tickedLabel,
    offers: [offer],
  }
}

/** Whether the bar offers a button for it: what Paste would run. */
export function usable(offer: PasteOffer): boolean {
  return offer.available || offer.name_conflict === true
}

/** What an item says beside its button, or instead of one. */
export function itemDetail(offer: PasteOffer, intent: CrossPasteIntent): string {
  if (!usable(offer)) return offer.reason ?? t("workspace.pair.not_possible")
  return t("workspace.pair.into", { what: intent.sourceLabel, where: offerPlace(offer, intent) })
}

