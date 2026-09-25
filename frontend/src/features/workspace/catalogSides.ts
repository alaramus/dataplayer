/**
 * Where each open catalog stands and what is ticked in it, for whatever reads
 * two catalogs at once (D167).
 *
 * Published by the catalog panel itself rather than read out of it: the pair
 * window holds the two panels and is not their parent, and the state lives in
 * each panel's own level. Module-level for the reason the clipboard is: small,
 * one writer per panel, and Pinia is for what one screen shares with another.
 */

import { computed, reactive } from "vue"

export interface CatalogSide {
  connectorId: string
  /** The place Paste would act on; null is the top of the connection. */
  place: string | null
  placeLabel: string
  ticked: string[]
  tickedLabel: string
}

const sides = reactive(new Map<string, CatalogSide>())

export function publishSide(panelId: string, side: CatalogSide | null): void {
  if (side === null) sides.delete(panelId)
  else sides.set(panelId, side)
}

export function useCatalogSide(panelId: () => string) {
  return computed(() => sides.get(panelId()) ?? null)
}
