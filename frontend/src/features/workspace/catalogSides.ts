/**
 * Where each open catalog stands and what is ticked in it, for whatever reads
 * a catalog from outside it: a pair of two (D167), a search scoped to one
 * (D205).
 *
 * Published by the catalog panel itself rather than read out of it: the pair
 * window holds the two panels and is not their parent, and the state lives in
 * each panel's own level. Module-level for the reason the clipboard is: small,
 * one writer per panel, and Pinia is for what one screen shares with another.
 */

import { computed, reactive } from "vue"

import type { ActionOutcome } from "@/features/catalog/actions"

export interface CatalogSide {
  connectorId: string
  /** The place Paste would act on; null is the top of the connection. */
  place: string | null
  placeLabel: string
  ticked: string[]
  tickedLabel: string
  /**
   * Where the catalog's own search starts, and so a search scoped to it
   * (D205): the level it stands on, or the grouping a tree is rooted in.
   */
  searchFrom: string | null
}

const sides = reactive(new Map<string, CatalogSide>())

export function publishSide(panelId: string, side: CatalogSide | null): void {
  if (side === null) sides.delete(panelId)
  else sides.set(panelId, side)
}

/** Where a catalog stands for a search scoped to it (D205): null at its top or unknown. */
export function searchFromOf(panelId: string): string | null {
  return sides.get(panelId)?.searchFrom ?? null
}

export function useCatalogSide(panelId: () => string) {
  return computed(() => sides.get(panelId()) ?? null)
}

// Apart from the sides: a side is part of a query key, and a function in one
// would be a key nothing can hash.
const settlers = new Map<string, (outcome: ActionOutcome | null) => void>()

/**
 * How a catalog lets go of its ticks once a pair has done what they chose;
 * null forgets it. An outcome narrows the ticks as an action of the catalog's
 * own does, and none takes them all off.
 */
export function offerSettle(
  panelId: string,
  settle: ((outcome: ActionOutcome | null) => void) | null
): void {
  if (settle === null) settlers.delete(panelId)
  else settlers.set(panelId, settle)
}

export function settleSide(panelId: string, outcome: ActionOutcome | null): void {
  settlers.get(panelId)?.(outcome)
}
