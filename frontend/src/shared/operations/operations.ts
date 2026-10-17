import { shallowRef } from "vue"

import { t } from "@/shared/i18n"
import { newId } from "@/shared/ids"

export type OperationState = "running" | "pausing" | "paused" | "stopping" | "succeeded" | "failed" | "cancelled"

export interface Operation {
  id: string
  label: string
  detail: string
  state: OperationState
  total: number
  completed: number
  transfer: { loaded: number; total: number } | null
  createdAt: number
  canPause: boolean
  canStop: boolean
}

export function isActive(operation: Pick<Operation, "state">): boolean {
  return ["running", "pausing", "paused", "stopping"].includes(operation.state)
}

/** Local requests only. Durable server jobs belong to vue-query. */
export function createOperations() {
  const items = shallowRef<Operation[]>([])
  const controls = new Map<string, { pause(): void; resume(): void; stop(): void }>()

  function trim() {
    let finished = 0
    items.value = items.value.filter((item) => isActive(item) || ++finished <= 50)
  }

  function start(label: string, total: number) {
    const id = newId()
    let current: Operation = {
      id, label, detail: t("notifications.operations.starting"), state: "running", total, completed: 0,
      transfer: null, createdAt: Date.now(), canPause: total > 1, canStop: total > 1,
    }
    let inFlight = false
    let paused = false
    let stopped = false
    let wake: (() => void) | undefined
    items.value = [current, ...items.value]

    function update(patch: Partial<Operation>) {
      current = { ...current, ...patch }
      items.value = items.value.map((item) => item.id === id ? current : item)
    }
    function remaining() {
      return current.total - current.completed - Number(inFlight)
    }
    const control = {
      pause() {
        if (!isActive(current) || stopped || remaining() <= 0) return
        paused = true
        update({ state: inFlight ? "pausing" : "paused", canPause: false })
      },
      resume() {
        if (!paused || stopped) return
        paused = false
        update({ state: "running", canPause: remaining() > 0 })
        wake?.()
      },
      stop() {
        if (!isActive(current)) return
        stopped = true
        paused = false
        update({ state: "stopping", canPause: false, canStop: false })
        wake?.()
      },
    }
    controls.set(id, control)

    function settle(state: "succeeded" | "failed" | "cancelled", detail: string) {
      update({ state, detail, transfer: null, canPause: false, canStop: false })
      controls.delete(id)
      // Retention follows completion, not start time: a long-running job
      // must not disappear as soon as it finishes behind fifty short ones.
      if (items.value.some((item) => item.id === id)) {
        items.value = [current, ...items.value.filter((item) => item.id !== id)]
      }
      trim()
    }

    return {
      id,
      /** A checkpoint before dispatch, never cancellation of a sent request. */
      async next(detail: string): Promise<boolean> {
        if (paused && !stopped) {
          update({ state: "paused", detail: t("notifications.operations.waiting_to_resume"), transfer: null })
          await new Promise<void>((resolve) => { wake = resolve })
          wake = undefined
        }
        if (stopped) return false
        inFlight = true
        update({ detail, transfer: null, canPause: remaining() > 0, canStop: remaining() > 0 })
        return true
      },
      transfer(loaded: number, totalBytes: number | undefined) {
        if (!inFlight || !isActive(current)) return
        if (!Number.isFinite(loaded)) return
        if (totalBytes === undefined || !Number.isFinite(totalBytes) || totalBytes <= 0) return
        const sent = Math.min(totalBytes, Math.max(0, loaded))
        update({
          transfer: { loaded: sent, total: totalBytes },
          ...(sent >= totalBytes ? { detail: t("notifications.operations.upload_sent") } : {}),
        })
      },
      complete() {
        inFlight = false
        update({ completed: current.completed + 1, transfer: null })
      },
      finish(detail: string, failed = false) {
        const state = stopped && current.completed < total ? "cancelled" : failed ? "failed" : "succeeded"
        settle(state, detail)
      },
      fail(detail: string) {
        settle("failed", detail)
      },
    }
  }

  return {
    items,
    start,
    pause: (id: string) => controls.get(id)?.pause(),
    resume: (id: string) => controls.get(id)?.resume(),
    stop: (id: string) => controls.get(id)?.stop(),
    clearFinished() { items.value = items.value.filter(isActive) },
    clear() {
      for (const control of controls.values()) control.stop()
      controls.clear()
      items.value = []
    },
  }
}

export type Operations = ReturnType<typeof createOperations>
export type OperationHandle = ReturnType<Operations["start"]>
