import { h } from "vue"
import type { Component } from "vue"

import ConfirmPrompt from "./ConfirmPrompt.vue"
import type { OpenWindow, WindowsApi } from "./useWindows"

export interface ConfirmRequest {
  title: string
  message: string
  confirmLabel?: string
  /**
   * What refusing means, when it means something.
   *
   * "Cancel" is right when nothing happens either way; when declining is
   * itself a choice — keeping a transaction open — it is named.
   */
  cancelLabel?: string
  danger?: boolean
}

/** Reusable geometry and behaviour for short questions. */
export function questionWindowPreset(
  id: string,
  title: string,
  component: Component
): OpenWindow {
  return {
    id,
    look: { title, icon: "help_outline" },
    size: { width: 420, height: 180 },
    minSize: { width: 320, height: 140 },
    component,
  }
}

/** Destructive questions share one recognisable icon and compact geometry. */
export function deleteWindowPreset(
  id: string,
  title: string,
  component: Component
): OpenWindow {
  return {
    ...questionWindowPreset(id, title, component),
    look: { title, icon: "warning_amber" },
  }
}

let confirmations = 0

/** Open a standard question in the shared floating-window host. */
export function confirmInWindow(
  windows: WindowsApi,
  request: ConfirmRequest
): Promise<boolean> {
  return new Promise((resolve) => {
    const id = `confirm:${(confirmations += 1)}`
    let settled = false
    const answer = (value: boolean) => {
      if (settled) return
      settled = true
      windows.close(id)
      resolve(value)
    }
    const component: Component = {
      name: `ConfirmPrompt-${id}`,
      setup: () => () => h(ConfirmPrompt, { request, onAnswer: answer }),
    }
    const preset = request.danger === true ? deleteWindowPreset : questionWindowPreset
    windows.open({
      ...preset(id, request.title, component),
      onClosed: () => {
        if (settled) return
        settled = true
        resolve(false)
      },
    })
  })
}
