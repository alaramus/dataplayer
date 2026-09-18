import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { Ref } from "vue"

import { clampRailWidth, parseRailNarrow, parseRailWidth, RAIL_NARROW_PX } from "./railWidth"

/** Where a rail keeps its width and whether it is pushed aside. */
export interface SideRailKeys {
  width: string
  narrow: string
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // A courtesy, not state: the rail still resizes, it just forgets.
  }
}

/**
 * A rail beside the main card of a space (D125, D141): dragged wider and
 * narrower by the gap beside it, pushed aside to its icons, held to the space
 * it is drawn in, and remembered under the keys the caller names — which is
 * where the caller scopes them, to a server or to nothing.
 *
 * `element` is that space; its width is what the rail is held to, so a window
 * made narrower narrows the rail too, while what is stored is what was dragged
 * to. Pushed aside, the rail keeps that width for when it comes back.
 */
export function useSideRail(element: Readonly<Ref<HTMLElement | null>>, keys: SideRailKeys) {
  const width = ref(parseRailWidth(read(keys.width)))
  const narrow = ref(parseRailNarrow(read(keys.narrow)))
  const spaceWidth = ref(0)
  const shownWidth = computed(() =>
    narrow.value ? RAIL_NARROW_PX : clampRailWidth(width.value, spaceWidth.value)
  )

  const observer = new ResizeObserver((entries) => {
    const entry = entries[0]
    if (entry !== undefined) spaceWidth.value = entry.contentRect.width
  })
  onMounted(() => {
    if (element.value !== null) observer.observe(element.value)
  })
  onBeforeUnmount(() => {
    observer.disconnect()
  })

  function resize(deltaPx: number) {
    if (!narrow.value) width.value = clampRailWidth(shownWidth.value + deltaPx, spaceWidth.value)
  }

  // A press on the gap beside a pushed-aside rail brings it back, as the
  // border of a collapsed workspace column does.
  function pressGap() {
    if (narrow.value) narrow.value = false
  }

  watch(width, (value) => {
    write(keys.width, String(value))
  })
  watch(narrow, (value) => {
    write(keys.narrow, value ? "narrow" : "wide")
  })

  return { narrow, shownWidth, resize, pressGap }
}
