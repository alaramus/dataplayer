import { readonly, ref, watch } from "vue"
import type { InjectionKey } from "vue"

import type { ConnectorPublic } from "@/client"
import { nextId } from "@/shared/workspace"
import type { WorkspaceApi } from "@/shared/workspace"

import { catalogPanelId } from "./panels"
import type { Panel } from "./panels"
import { dropOnPair, pairCommand, pairIntact, swapped } from "./pairs"
import type { Pair, PairCandidate, PairCommand } from "./pairs"

/**
 * The waiting pair and the open ones, over the workspace engine (D167).
 *
 * A pair is two catalog panels torn off as one group: the engine keeps them
 * out of the layout and docks them back, and the window around them is drawn
 * by `PairWindows`. What is waiting is only remembered — its catalog stays
 * where it was until the second one arrives.
 */
export function usePairs(
  workspace: WorkspaceApi<Panel>,
  openCatalog: (connector: ConnectorPublic) => void
) {
  const context = workspace.context
  const waiting = ref<PairCandidate | null>(null)
  const pairs = ref<Pair[]>([])

  function candidateOf(panelId: string): PairCandidate | null {
    const panel = workspace.panels.value.find((one) => one.id === panelId)
    return panel?.kind === "catalog"
      ? { panelId, connectorId: panel.connectorId, title: panel.title }
      : null
  }

  /** A catalog's own Pair command pressed. */
  function offer(panelId: string) {
    const carried = candidateOf(panelId)
    if (carried === null) return
    const answer = dropOnPair(waiting.value, carried)
    if (answer.kind === "hold") waiting.value = carried
    else if (answer.kind === "complete") open(answer.left, answer.right)
  }

  /** What that command says now, which follows whatever is waiting. */
  function commandOf(panelId: string): PairCommand {
    const candidate = candidateOf(panelId)
    return candidate === null
      ? { tooltip: "Pair with another connection", refused: true }
      : pairCommand(waiting.value, candidate)
  }

  /** The second side chosen from a list rather than carried. */
  function pairWith(connector: ConnectorPublic) {
    openCatalog(connector)
    offer(catalogPanelId(connector.id))
  }

  function cancel() {
    waiting.value = null
  }

  function open(left: PairCandidate, right: PairCandidate) {
    const id = nextId("pair")
    for (const side of [left, right]) {
      // Already floating — alone, or in another pair — it comes home first,
      // since only a panel in the layout can be torn off.
      if (context.detached.value.some((entry) => entry.panelId === side.panelId)) {
        context.dock(side.panelId)
      }
    }
    if (!context.canDetach(left.panelId) || !context.canDetach(right.panelId)) return
    context.detach(left.panelId, id)
    context.detach(right.panelId, id)
    pairs.value = [...pairs.value, { id, left, right }]
    waiting.value = null
  }

  /** Both catalogs back to the catalog column, where D93 returns them. */
  function unpair(pairId: string) {
    const pair = pairs.value.find((one) => one.id === pairId)
    if (pair === undefined) return
    pairs.value = pairs.value.filter((one) => one.id !== pairId)
    for (const side of [pair.left, pair.right]) {
      if (context.detached.value.some((entry) => entry.panelId === side.panelId && entry.group === pairId)) {
        context.dock(side.panelId)
      }
    }
  }

  function swap(pairId: string) {
    pairs.value = pairs.value.map((one) => one.id === pairId ? swapped(one) : one)
  }

  // Closing the waiting catalog forgets it.
  watch(
    () => workspace.panels.value.map((panel) => panel.id),
    (ids) => {
      if (waiting.value !== null && !ids.includes(waiting.value.panelId)) waiting.value = null
    }
  )

  // A catalog that left its pair by any other way — closed with its
  // connection, say — takes the pair with it; the other one goes home.
  watch(
    () => context.detached.value,
    (entries) => {
      for (const pair of pairs.value) {
        const grouped = new Set(
          entries.filter((entry) => entry.group === pair.id).map((entry) => entry.panelId)
        )
        if (!pairIntact(pair, grouped)) unpair(pair.id)
      }
    }
  )

  return {
    waiting: readonly(waiting),
    pairs: readonly(pairs),
    candidateOf,
    offer,
    commandOf,
    pairWith,
    cancel,
    unpair,
    swap,
  }
}

export type PairsApi = ReturnType<typeof usePairs>

export const pairsKey: InjectionKey<PairsApi> = Symbol("pairs")
