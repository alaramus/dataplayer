import { shallowRef } from "vue"
import type { InjectionKey } from "vue"

export interface PanelTarget {
  panelId: string
  element: HTMLElement
}

export function createPanelTargets() {
  const targets = shallowRef<ReadonlyMap<string, PanelTarget>>(new Map())
  function set(id: string, target: PanelTarget | null) {
    const next = new Map(targets.value)
    if (target === null) next.delete(id)
    else next.set(id, target)
    targets.value = next
  }
  return { targets, set }
}

export const panelTargetsKey: InjectionKey<ReturnType<typeof createPanelTargets>> = Symbol("panel-targets")
