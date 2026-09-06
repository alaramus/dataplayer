import { notices } from "@/shared/notifications/notices"

/**
 * A transient message, named by what happened rather than by its colour.
 *
 * Screens used to call `notify({ type: "positive" })` directly, which meant
 * every screen deciding what a success looks like.
 *
 * What the four functions do now is write to the log behind the activity
 * sheet (D114). Whether anything appears on screen, where, and for how long is
 * that store's decision — a screen that says something is not the place to
 * decide whether the person is being disturbed.
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
  const log = notices()

  return {
    success: (message) => {
      log.record({ tone: "success", message, sticky: false, action: null })
    },
    // An error does not fade: the one message worth reading is the one most
    // likely to be missed, and it is still in the sheet either way.
    error: (message) => {
      log.record({ tone: "error", message, sticky: true, action: null })
    },
    info: (message) => {
      log.record({ tone: "info", message, sticky: false, action: null })
    },
    offer: (message, action) => {
      log.record({
        tone: "info",
        message,
        sticky: true,
        action: { label: action.label, run: action.onClick },
      })
    },
  }
}
