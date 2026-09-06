import { onScopeDispose, ref } from "vue"
import type { Ref } from "vue"

/**
 * A mark that takes itself off after a few seconds.
 *
 * Held indefinitely it stops saying "here it is" and starts reading as a state
 * of the row — a second kind of selection beside the tick boxes, which mean
 * something else. A composable of its own, so the timing is tested with a fake
 * clock and without mounting anything.
 */
export interface FadingMark<T> {
  value: Readonly<Ref<T | null>>
  show: (what: T) => void
  clear: () => void
}

export function useFadingMark<T>(afterMs: number): FadingMark<T> {
  const value = ref<T | null>(null) as Ref<T | null>
  let timer: ReturnType<typeof setTimeout> | null = null

  function stopTimer() {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function clear() {
    stopTimer()
    value.value = null
  }

  function show(what: T) {
    // From the start, not from whatever was left of the previous mark's time.
    stopTimer()
    value.value = what
    timer = setTimeout(clear, afterMs)
  }

  // A timer outliving the panel would write into a ref nobody reads.
  onScopeDispose(stopTimer)

  return { value, show, clear }
}
