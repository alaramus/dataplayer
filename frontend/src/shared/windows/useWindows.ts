import { computed, onScopeDispose, ref, shallowRef } from "vue"
import type { Component, InjectionKey, Ref } from "vue"

import { bringToFront, clamp, place } from "./geometry"
import type { Rect, Size } from "./geometry"

/**
 * Floating windows over the application.
 *
 * The engine knows nothing about what a window holds: a feature hands it an
 * id, a size, a look and a component, the same split that keeps
 * `shared/workspace` free of any knowledge of panels.
 *
 * Windows are not modal, and that is the requirement rather than a detail:
 * one connection is read while another is filled in beside it. What
 * modality would have given — you cannot walk away from an unfinished form —
 * is replaced by asking before a window with unsaved changes is closed, which
 * is the feature's business and not the engine's.
 */

export interface WindowLook {
  title: string
  icon?: string
}

export interface OpenWindow {
  id: string
  look: WindowLook
  size: Size
  component: Component
}

export interface WindowState extends OpenWindow {
  rect: Rect
  /**
   * What this window *is*, as opposed to what it shows.
   *
   * Fixed for as long as the window lives, while `id` may change — a saved
   * draft becomes the window of the connection it created. Keying the list by
   * `id` unmounted the window at that moment and mounted a fresh one: the
   * form reset itself, and the close that followed the save was delivered to
   * an instance that no longer existed.
   */
  key: string
}

export interface WindowsContext {
  /** Back to front, so the last one is on top. */
  windows: Ref<WindowState[]>
  frontId: Ref<string | null>
  focus: (id: string) => void
  close: (id: string) => void
  move: (id: string, to: { x: number; y: number }) => void
  /** Ask before closing, answered by the feature. Null means "just close". */
  confirmClose: ((id: string) => Promise<boolean>) | null
}

export const windowsKey: InjectionKey<WindowsContext> = Symbol("windows")

function viewportSize(): Size {
  return { width: window.innerWidth, height: window.innerHeight }
}

export interface WindowsApi {
  context: WindowsContext
  /**
   * Show a window, or bring the one already showing it to the front.
   *
   * Never a second window for the same id. Two windows of one connection are
   * two unsaved edits of one row, and whichever is saved second silently
   * wins — see the spec, O2.
   */
  open: (window: OpenWindow) => void
  close: (id: string) => void
  isOpen: (id: string) => boolean
  /** Replace a window's id, keeping its place: a saved draft becomes the
   *  window of the connection it created, so a second save updates it. */
  rename: (from: string, to: string, look: WindowLook) => void
}

export function useWindows(
  options: { confirmClose?: (id: string) => Promise<boolean> } = {}
): WindowsApi {
  // shallowRef: a window carries a component, and making that deeply reactive
  // would walk the whole component definition.
  const windows = shallowRef<WindowState[]>([])
  const order = ref<string[]>([])
  let keys = 0

  function ordered(): WindowState[] {
    const byId = new Map(windows.value.map((entry) => [entry.id, entry]))
    return order.value.flatMap((id) => {
      const found = byId.get(id)
      return found === undefined ? [] : [found]
    })
  }

  function focus(id: string) {
    order.value = bringToFront(order.value, id)
    windows.value = ordered()
  }

  function isOpen(id: string) {
    return windows.value.some((entry) => entry.id === id)
  }

  function open(window: OpenWindow) {
    if (isOpen(window.id)) {
      focus(window.id)
      return
    }
    const last = windows.value[windows.value.length - 1]?.rect ?? null
    const rect = place(window.size, last, viewportSize())
    keys += 1
    windows.value = [...windows.value, { ...window, rect, key: `w${keys}` }]
    order.value = [...order.value, window.id]
  }

  function close(id: string) {
    windows.value = windows.value.filter((entry) => entry.id !== id)
    order.value = order.value.filter((other) => other !== id)
  }

  function move(id: string, to: { x: number; y: number }) {
    const viewport = viewportSize()
    windows.value = windows.value.map((entry) =>
      entry.id === id ? { ...entry, rect: clamp({ ...entry.rect, ...to }, viewport) } : entry
    )
  }

  function rename(from: string, to: string, look: WindowLook) {
    if (from === to) return
    windows.value = windows.value.map((entry) =>
      entry.id === from ? { ...entry, id: to, look } : entry
    )
    order.value = order.value.map((other) => (other === from ? to : other))
  }

  // A window that was reachable can stop being so when the browser window is
  // made smaller under it, so the rule is applied again rather than only at
  // the moment of a drag.
  function reclamp() {
    const viewport = viewportSize()
    windows.value = windows.value.map((entry) => ({
      ...entry,
      rect: clamp(entry.rect, viewport),
    }))
  }

  window.addEventListener("resize", reclamp)
  onScopeDispose(() => window.removeEventListener("resize", reclamp))

  const frontId = computed(() => windows.value[windows.value.length - 1]?.id ?? null)

  return {
    context: {
      windows,
      frontId,
      focus,
      close,
      move,
      confirmClose: options.confirmClose ?? null,
    },
    open,
    close,
    isOpen,
    rename,
  }
}
