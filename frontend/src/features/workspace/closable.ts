import { inject, onUnmounted, provide } from "vue"
import type { InjectionKey } from "vue"

/**
 * Which panels may not simply go.
 *
 * The same shape as the reload registry beside it, and for the same reason:
 * the engine knows a tab is being closed, and what that costs is the feature's
 * knowledge. A console holding an open transaction is the case that made this
 * exist — closing it would leave a lease running with nobody watching (D66).
 */
export type CloseGuard = () => Promise<boolean> | boolean

export interface CloseRegistry {
  /** Say when this panel may go. Returns the way to take it back. */
  register(panelId: string, guard: CloseGuard): () => void
  /** Whether this panel may go now. True when nothing said otherwise. */
  mayClose(panelId: string): Promise<boolean>
}

export function createCloseRegistry(): CloseRegistry {
  const guards = new Map<string, CloseGuard>()

  function register(panelId: string, guard: CloseGuard): () => void {
    guards.set(panelId, guard)
    return () => {
      // Only if it is still ours, as the reload registry does: a remount
      // registers before the old copy is torn down.
      if (guards.get(panelId) === guard) guards.delete(panelId)
    }
  }

  async function mayClose(panelId: string): Promise<boolean> {
    const guard = guards.get(panelId)
    if (guard === undefined) return true
    return await guard()
  }

  return { register, mayClose }
}

const closeRegistryKey: InjectionKey<CloseRegistry> = Symbol("close-registry")

export function provideCloseRegistry(registry: CloseRegistry) {
  provide(closeRegistryKey, registry)
}

/**
 * Say when this panel may be closed, for as long as it exists.
 *
 * Called from the panel's own setup, like `useReloadable`. A panel that says
 * nothing may always go.
 */
export function useClosable(panelId: string, guard: CloseGuard) {
  const registry = inject(closeRegistryKey, null)
  if (registry === null) return
  const forget = registry.register(panelId, guard)
  onUnmounted(forget)
}
