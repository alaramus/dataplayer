import { computed, inject, nextTick, onScopeDispose, provide, ref, shallowRef } from "vue"
import type { Component, InjectionKey, Ref } from "vue"

import {
  FIT_MARGIN,
  bringToFront,
  clamp,
  fit,
  place,
  resize,
  resizeTo,
} from "./geometry"
import type { Rect, ResizeEdge, Size } from "./geometry"

/**
 * Floating windows over the application. The engine knows nothing about what a
 * window holds — an id, a size, a look and a component — the same split that
 * keeps `shared/workspace` free of any knowledge of panels.
 *
 * Windows are not modal, and that is the requirement: one connection is read
 * while another is filled in beside it. What modality would have given is
 * replaced by asking before a window with unsaved changes is closed, which is
 * the feature's business and not the engine's.
 */

export interface WindowLook {
  title: string
  icon?: string
  color?: string | null
}

/**
 * One command of a window's own, drawn in its bar beside the size controls.
 *
 * What a window *is* rather than what it holds: returning a detached panel to
 * the workspace belongs with minimize, maximize and close, because all four
 * are about the frame and none of them is about the rows inside it. The engine
 * knows only the icon, the words and what to call — which feature supplies it
 * and what pressing it does are none of its business (D112).
 */
export interface WindowAction {
  icon: string
  tooltip: string
  /** How a test addresses it; the window's own id is appended by the frame. */
  testid?: string
  run: () => void
}

export interface OpenWindow {
  id: string
  look: WindowLook
  size: Size
  component: Component
  /** Stable forms keep their preferred rectangle as their content changes (D132). */
  sizing?: "content" | "stable"
  /**
   * Commands of this window's own, before the size controls in its bar.
   *
   * Read on every render, so a closure over a ref stays right when what the
   * window shows is replaced.
   */
  actions?: WindowAction[]
  /** Follow rendered content size until the user manually resizes the window. */
  autoFit?: boolean
  minSize?: Size
  /**
   * Escape asks this window to close, as the cross does.
   *
   * A question only. No form in this application closes on Escape, which is
   * deliberate and stated in workspace.md: one gesture for a connection window
   * and for a form is worth more than matching what a modal used to do. A
   * question is the case that argument was never about - it holds nothing that
   * a press could lose, and Escape is the way out everybody reaches for (U12).
   */
  dismissible?: boolean
  beforeClose?: () => boolean | Promise<boolean>
  /** The user returns to this window, even when it is already frontmost. */
  onFocus?: () => void
  onClosed?: () => void
}

export interface WindowState extends OpenWindow {
  rect: Rect
  hasFit: boolean
  minimized: boolean
  /** The normal rectangle stays in rect while the frame fills the viewport. */
  maximized: boolean
  /**
   * What this window *is*, as opposed to what it shows.
   *
   * Fixed for as long as the window lives, while `id` may change — a saved
   * draft becomes the window of the connection it created. Keying the list by
   * `id` unmounted the window at that moment and mounted a fresh one: the
   * form reset itself, and the close that followed the save was delivered to
   * an instance that no longer existed.
   *
   * A rising number rather than a string, so the taskbar can put the windows
   * back into the order they were opened in: the list itself is kept in
   * stacking order and rearranges under the pointer.
   */
  key: number
}

export interface WindowsContext {
  /** Back to front, so the last one is on top. */
  windows: Ref<WindowState[]>
  frontId: Ref<string | null>
  bottomInset: Ref<number>
  focus: (id: string) => void
  minimize: (id: string) => void
  toggleMaximize: (id: string) => void
  close: (id: string) => void
  requestClose: (id: string) => Promise<void>
  move: (id: string, to: { x: number; y: number }) => void
  resize: (id: string, edge: ResizeEdge, pointer: { x: number; y: number }) => void
  fit: (id: string, size: Size) => void
  /** Ask before closing, answered by the feature. Null means "just close". */
  confirmClose: ((id: string) => Promise<boolean>) | null
}

export const windowsKey: InjectionKey<WindowsContext> = Symbol("windows")
export const windowsApiKey: InjectionKey<WindowsApi> = Symbol("windows-api")

export function provideWindows(api: WindowsApi): void {
  provide(windowsApiKey, api)
}

export function useWindowManager(): WindowsApi {
  const api = inject(windowsApiKey)
  if (api === undefined) throw new Error("No floating window host was provided")
  return api
}

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
  /**
   * Change what an open window calls itself, and nothing else.
   *
   * A heading is part of the answer: a form that asks where rows should go
   * says "table" or "file" once the destination is picked, and a frame still
   * saying the other one has already misled the reader.
   */
  retitle: (id: string, look: WindowLook) => void
  /** Space reserved by the application footer, measured by its layout. */
  setBottomInset: (height: number) => void
}

export function useWindows(
  options: { confirmClose?: (id: string) => Promise<boolean> } = {}
): WindowsApi {
  // shallowRef: a window carries a component, and making that deeply reactive
  // would walk the whole component definition.
  const windows = shallowRef<WindowState[]>([])
  const order = ref<string[]>([])
  const bottomInset = ref(0)
  let keys = 0
  /**
   * Where the keyboard was when each window opened (U12).
   *
   * Beside the windows rather than in them: a DOM node kept in state would be
   * drawn into whatever watches that state, and this is a note to give focus
   * back with, not part of what a window is.
   */
  const openedFrom = new Map<string, HTMLElement>()

  /**
   * The control the keyboard is really on.
   *
   * Quasar puts the focus of a pressed button into a hidden span inside it, so
   * what `document.activeElement` answers is not a place a person could be
   * sent back to - a negative tabindex is nowhere - and the control around it
   * is what asked the question.
   */
  const FOCUSABLE = 'button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  function controlOf(node: Element | null): HTMLElement | null {
    return node instanceof HTMLElement ? node.closest<HTMLElement>(FOCUSABLE) : null
  }

  function ordered(): WindowState[] {
    const byId = new Map(windows.value.map((entry) => [entry.id, entry]))
    return order.value.flatMap((id) => {
      const found = byId.get(id)
      return found === undefined ? [] : [found]
    })
  }

  function focus(id: string) {
    windows.value = windows.value.map((entry) =>
      entry.id === id && entry.minimized ? { ...entry, minimized: false } : entry
    )
    order.value = bringToFront(order.value, id)
    windows.value = ordered()
    windows.value.find((entry) => entry.id === id)?.onFocus?.()
  }

  function minimize(id: string) {
    windows.value = windows.value.map((entry) =>
      entry.id === id ? { ...entry, minimized: true } : entry
    )
  }

  function toggleMaximize(id: string) {
    windows.value = windows.value.map((entry) =>
      entry.id === id
        ? { ...entry, maximized: !entry.maximized, rect: clamp(entry.rect, viewportSize()) }
        : entry
    )
    focus(id)
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
    const viewport = viewportSize()
    const placed = place(window.size, last, viewport)
    const rect = window.sizing === "stable" ? resizeTo(placed, placed, viewport) : placed
    keys += 1
    windows.value = [
      ...windows.value,
      {
        ...window,
        autoFit: window.sizing === "stable" ? false : window.autoFit ?? true,
        rect,
        hasFit: false,
        minimized: false,
        maximized: false,
        key: keys,
      },
    ]
    order.value = [...order.value, window.id]
    const from = controlOf(document.activeElement)
    if (from !== null) openedFrom.set(window.id, from)
    window.onFocus?.()
  }

  function close(id: string) {
    windows.value.find((entry) => entry.id === id)?.onClosed?.()
    windows.value = windows.value.filter((entry) => entry.id !== id)
    order.value = order.value.filter((other) => other !== id)
    giveFocusBack(id)
  }

  /**
   * The command that opened a window gets the keyboard back when it closes.
   *
   * Once the frame is gone the browser has dropped focus on the body, and only
   * then is it anybody's to give: somebody who has moved on somewhere else
   * keeps where they are. An opener that has itself gone from the page - a
   * row that was deleted, a tab that was closed - is left alone too.
   */
  function giveFocusBack(id: string) {
    const from = openedFrom.get(id)
    openedFrom.delete(id)
    if (from === undefined) return
    void nextTick(() => {
      const now = document.activeElement
      if (now !== null && now !== document.body) return
      if (from.isConnected) from.focus({ preventScroll: true })
    })
  }

  async function requestClose(id: string) {
    const entry = windows.value.find((one) => one.id === id)
    if (entry === undefined) return
    if (entry.beforeClose !== undefined && !(await entry.beforeClose())) return
    if (entry.beforeClose === undefined && options.confirmClose && !(await options.confirmClose(id))) return
    close(id)
  }

  function move(id: string, to: { x: number; y: number }) {
    const viewport = viewportSize()
    windows.value = windows.value.map((entry) =>
      entry.id === id && !entry.minimized && !entry.maximized
        ? { ...entry, rect: clamp({ ...entry.rect, ...to }, viewport) }
        : entry
    )
  }

  function resizeWindow(id: string, edge: ResizeEdge, pointer: { x: number; y: number }) {
    const viewport = viewportSize()
    windows.value = windows.value.map((entry) =>
      entry.id === id && !entry.minimized && !entry.maximized
        ? {
            ...entry,
            autoFit: false,
            rect: resize(
              entry.rect,
              edge,
              pointer,
              viewport,
              entry.minSize ?? { width: 280, height: 160 }
            ),
          }
        : entry
    )
  }

  function fitWindow(id: string, size: Size) {
    const viewport = viewportSize()
    windows.value = windows.value.map((entry) => {
      if (entry.id !== id || entry.autoFit === false || entry.minimized || entry.maximized) return entry
      const minimum = entry.minSize ?? { width: 280, height: 160 }
      const wanted = {
        width: Math.max(minimum.width, size.width),
        // Leave a small moving margin even when the contents are taller than
        // the viewport (FIT_MARGIN).
        height: Math.min(
          Math.max(minimum.height, size.height),
          Math.max(minimum.height, viewport.height - FIT_MARGIN)
        ),
      }
      return {
        ...entry,
        rect: entry.hasFit
          ? resizeTo(entry.rect, wanted, viewport)
          : fit(entry.rect, wanted, viewport),
        hasFit: true,
      }
    })
  }

  function rename(from: string, to: string, look: WindowLook) {
    if (from === to) return
    windows.value = windows.value.map((entry) =>
      entry.id === from ? { ...entry, id: to, look } : entry
    )
    order.value = order.value.map((other) => (other === from ? to : other))
    // The window is the same window: what opened it is still what to give the
    // keyboard back to, and an entry left under the old name is a held node
    // nothing would ever come for.
    const opener = openedFrom.get(from)
    openedFrom.delete(from)
    if (opener !== undefined) openedFrom.set(to, opener)
  }

  function retitle(id: string, look: WindowLook) {
    windows.value = windows.value.map((entry) =>
      entry.id === id ? { ...entry, look } : entry
    )
  }

  // A window that was reachable can stop being so when the browser window is
  // made smaller under it, so the rule is applied again rather than only at
  // the moment of a drag.
  function reclamp() {
    const viewport = viewportSize()
    windows.value = windows.value.map((entry) => ({
      ...entry,
      rect: entry.sizing === "stable"
        ? resizeTo(entry.rect, entry.rect, viewport)
        : clamp(entry.rect, viewport),
    }))
  }

  window.addEventListener("resize", reclamp)
  onScopeDispose(() => window.removeEventListener("resize", reclamp))

  const frontId = computed(() => {
    const visible = windows.value.filter((entry) => !entry.minimized)
    return visible[visible.length - 1]?.id ?? null
  })

  return {
    context: {
      windows,
      frontId,
      bottomInset,
      focus,
      minimize,
      toggleMaximize,
      close,
      requestClose,
      move,
      resize: resizeWindow,
      fit: fitWindow,
      confirmClose: options.confirmClose ?? null,
    },
    open,
    close,
    isOpen,
    rename,
    retitle,
    setBottomInset: (height) => { bottomInset.value = Math.max(0, height) },
  }
}
