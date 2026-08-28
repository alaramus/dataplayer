import { confirmInWindow, useWindowManager } from "@/shared/windows"
import type { ConfirmRequest, WindowsApi } from "@/shared/windows"

export type { ConfirmRequest } from "@/shared/windows"

/**
 * Ask before doing something that cannot be taken back.
 *
 * A promise rather than Quasar's `.onOk()` chain: the caller then reads as
 * ordinary sequential code, and dismissing the dialog is the same answer as
 * cancelling instead of a third path each caller has to remember.
 */
export function useConfirm(api?: WindowsApi): (request: ConfirmRequest) => Promise<boolean> {
  const windows = api ?? useWindowManager()
  return (request) => confirmInWindow(windows, request)
}
