import { inject, onUnmounted, provide, toValue, watch } from "vue"
import type { InjectionKey, MaybeRefOrGetter } from "vue"

/**
 * Who knows how to re-read a panel: the panel, which registers here by id.
 *
 * Not component instance refs held by the engine — that would tie the engine
 * to the insides of panels, which is what D12 exists to prevent.
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

/** Null outside the workspace page: a panel mounted alone has nothing to press. */
export function useReloadRegistry(): ReloadRegistry | null {
  return inject(reloadRegistryKey, null)
}

/**
 * Called from the panel's own setup. A panel is kept alive while its tab is
 * not showing, so the registration survives switching away and back.
 *
 * Read rather than taken once, because a panel is named by what it holds and
 * is renamed in place when that changes — a console put into the library, a
 * workbook switched to another sheet. The component is deliberately not built
 * again for that (D65), so a registration left under the old name is a button
 * the engine can no longer find: it went quiet instead of failing.
 */
export function useReloadable(panelId: MaybeRefOrGetter<string>, reload: Reload) {
  const registry = inject(reloadRegistryKey, null)
  if (registry === null) return
  let forget = registry.register(toValue(panelId), reload)
  watch(
    () => toValue(panelId),
    (renamed) => {
      forget()
      forget = registry.register(renamed, reload)
    }
  )
  onUnmounted(() => forget())
}
