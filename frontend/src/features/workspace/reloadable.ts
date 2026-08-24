import { inject, onUnmounted, provide } from "vue"
import type { InjectionKey } from "vue"

/**
 * Who knows how to re-read a panel.
 *
 * The tab strip offers the button; what pressing it means belongs to the panel
 * — the connections list re-fetches a query, the catalog re-reads the level it
 * is standing on, the grid re-runs the page it is showing. So a panel says how,
 * and this holds the answers by panel id.
 *
 * Not component instance refs held by the engine: that would tie the engine to
 * the insides of panels, which is the thing D12 exists to prevent.
 */
export type Reload = () => Promise<void> | void

export interface ReloadRegistry {
  /** Say how this panel is re-read. Returns the way to take it back. */
  register(panelId: string, reload: Reload): () => void
  /** Re-read a panel. False when nothing was registered for it. */
  reload(panelId: string): Promise<boolean>
}

export function createReloadRegistry(): ReloadRegistry {
  const known = new Map<string, Reload>()

  function register(panelId: string, reload: Reload): () => void {
    known.set(panelId, reload)
    return () => {
      // Only if it is still ours. A remount registers before the old copy is
      // torn down, and an unconditional delete would then leave the panel that
      // is actually on screen with no way to be re-read.
      if (known.get(panelId) === reload) known.delete(panelId)
    }
  }

  async function reload(panelId: string): Promise<boolean> {
    const known_ = known.get(panelId)
    if (known_ === undefined) return false
    await known_()
    return true
  }

  return { register, reload }
}

const reloadRegistryKey: InjectionKey<ReloadRegistry> = Symbol("reload-registry")

export function provideReloadRegistry(registry: ReloadRegistry) {
  provide(reloadRegistryKey, registry)
}

/**
 * Say how this panel is re-read, for as long as it exists.
 *
 * Called from the panel's own setup. Panels are kept alive when their tab is
 * not showing, so the registration survives switching away and back; it goes
 * when the panel really goes.
 */
export function useReloadable(panelId: string, reload: Reload) {
  const registry = inject(reloadRegistryKey, null)
  if (registry === null) return
  const forget = registry.register(panelId, reload)
  onUnmounted(forget)
}
