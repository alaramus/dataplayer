import { useQuasar } from "quasar"

/**
 * A transient message, named by what happened rather than by its colour.
 *
 * Screens used to call `notify({ type: "positive" })` directly, which meant
 * every screen deciding what a success looks like.
 */
export interface Toast {
  success(message: string): void
  error(message: string): void
  info(message: string): void
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
  }
}
