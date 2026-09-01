import { useQuasar } from "quasar"

/**
 * A transient message, named by what happened rather than by its colour.
 *
 * Screens used to call `notify({ type: "positive" })` directly, which meant
 * every screen deciding what a success looks like.
 */
/** A way to act on what a message is about, offered beside it. */
export interface ToastAction {
  label: string
  onClick: () => void
}

export interface Toast {
  success(message: string): void
  error(message: string): void
  info(message: string): void
  /**
   * Something happened, and here is the way to deal with it.
   *
   * For news a person may want to act on at once — somebody asking for access
   * to a connection — where sending them hunting for the screen would be the
   * whole cost of the notification.
   */
  offer(message: string, action: ToastAction): void
}

export function useToast(): Toast {
  const quasar = useQuasar()

  return {
    success: (message) => {
      quasar.notify({ type: "positive", message })
    },
    error: (message) => {
      quasar.notify({ type: "negative", message })
    },
    info: (message) => {
      quasar.notify({ type: "info", message })
    },
    offer: (message, action) => {
      quasar.notify({
        type: "info",
        message,
        timeout: 0,
        actions: [
          { label: action.label, color: "white", handler: action.onClick },
          { label: "Dismiss", color: "white" },
        ],
      })
    },
  }
}
