import { appIcons } from "@/shared/ui/icons"

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
  /**
   * A tick box offering to stop asking, for a question worth asking once.
   *
   * `onRemember` runs only when the answer is yes: somebody who ticks the box
   * and then cancels has agreed to nothing, and remembering that would turn
   * the next press into the very thing they had just refused.
   */
  rememberLabel?: string
  onRemember?: () => void
  /**
   * A tick box that is part of the answer rather than about the question.
   *
   * `rememberLabel` asks whether to stop asking; this asks a second thing the
   * same press decides — whether removing a service takes its connection too.
   * So `onAlso` runs on yes whatever the box says, because "no" is one of its
   * two answers rather than the absence of one.
   */
  alsoLabel?: string
  alsoDefault?: boolean
  onAlso?: (chosen: boolean) => void
}

/** Reusable geometry and behaviour for short questions. */
export function questionWindowPreset(
  id: string,
  title: string,
  component: Component
): OpenWindow {
  return {
    id,
    look: { title, icon: appIcons.helpOutline },
    size: { width: 420, height: 200 },
    minSize: { width: 320, height: 160 },
    // A question holds nothing a press could lose.
    dismissible: true,
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
    look: { title, icon: appIcons.warningAmber },
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
