import { nextTick, onScopeDispose } from "vue"

import { serverNavigation } from "./profiles"

type LeaveGuard = () => boolean | Promise<boolean>

export function createLeaveGuards() {
  const guards = new Set<LeaveGuard>()
  return {
    register(guard: LeaveGuard) {
      guards.add(guard)
      return () => { guards.delete(guard) }
    },
    async mayLeave(): Promise<boolean> {
      for (const guard of [...guards]) if (!(await guard())) return false
      return true
    },
  }
}

const guards = createLeaveGuards()

export function useServerLeaveGuard(guard: LeaveGuard): void {
  onScopeDispose(guards.register(guard))
}

export function mayLeaveServer(): Promise<boolean> {
  return guards.mayLeave()
}

/** A new document is the boundary; no live client is ever retargeted. */
export async function switchServer(url: string, next = "/", beforeNavigate?: () => void): Promise<boolean> {
  const destination = serverNavigation(url, next)
  if (!(await mayLeaveServer())) return false
  await nextTick()
  beforeNavigate?.()
  window.location.assign(destination)
  return true
}
