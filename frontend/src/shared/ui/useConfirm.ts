import { useQuasar } from "quasar"

export interface ConfirmRequest {
  title: string
  message: string
  /** What the confirming button says. "Delete" reads better than "OK". */
  confirmLabel?: string
  /** Colours the confirming button as destructive. */
  danger?: boolean
}

/**
 * Ask before doing something that cannot be taken back.
 *
 * A promise rather than Quasar's `.onOk()` chain: the caller then reads as
 * ordinary sequential code, and dismissing the dialog is the same answer as
 * cancelling instead of a third path each caller has to remember.
 */
export function useConfirm(): (request: ConfirmRequest) => Promise<boolean> {
  const quasar = useQuasar()

  return (request) =>
    new Promise((resolve) => {
      quasar
        .dialog({
          title: request.title,
          message: request.message,
          cancel: true,
          ok: {
            label: request.confirmLabel ?? "Confirm",
            color: request.danger === true ? "negative" : "primary",
            noCaps: true,
          },
        })
        .onOk(() => {
          resolve(true)
        })
        // Fires for a dismissal as well as after onOk; resolving a settled
        // promise again is a no-op, so the first answer stands.
        .onDismiss(() => {
          resolve(false)
        })
    })
}
