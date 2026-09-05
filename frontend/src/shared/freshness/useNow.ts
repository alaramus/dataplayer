import { onScopeDispose, readonly, ref } from "vue"
import type { Ref } from "vue"

/**
 * One clock for everything that counts seconds on screen.
 *
 * A badge that says how old its data is has to be told that time passed. A
 * timer per badge would be one timer per open tab, all of them saying the
 * same second, so there is one interval and a count of who is watching it —
 * the last watcher to go away stops it.
 */
const now = ref(Date.now())
let watchers = 0
let ticking: ReturnType<typeof setInterval> | undefined

function start(): void {
  watchers += 1
  if (ticking !== undefined) return
  now.value = Date.now()
  ticking = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stop(): void {
  watchers = Math.max(watchers - 1, 0)
  if (watchers > 0 || ticking === undefined) return
  clearInterval(ticking)
  ticking = undefined
}

/** The current time, updated every second while this scope is alive. */
export function useNow(): Readonly<Ref<number>> {
  start()
  onScopeDispose(stop)
  return readonly(now)
}
