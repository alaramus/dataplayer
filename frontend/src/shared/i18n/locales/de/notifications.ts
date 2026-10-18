/** Benachrichtigungen und laufende Arbeit auf dem Bildschirm (shared/notifications, shared/operations). */
import type { Messages } from "../en"

export const notifications: Messages["notifications"] = {
  toasts: {
    more: "Noch {n} in „Aktivität“",
    dismiss: "Verwerfen",
  },
  operations: {
    starting: "Wird gestartet",
    waiting_to_resume: "Wartet auf Fortsetzung",
    upload_sent: "Upload gesendet; Warten auf den Server",
  },
}
