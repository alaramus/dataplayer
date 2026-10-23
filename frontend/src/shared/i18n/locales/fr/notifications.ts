/** Notifications et travail en cours à l'écran (shared/notifications, shared/operations). */
import type { Messages } from "../en"

export const notifications: Messages["notifications"] = {
  toasts: {
    more: "Encore {n} dans « Activité »",
    dismiss: "Ignorer",
  },
  operations: {
    starting: "Démarrage",
    waiting_to_resume: "En attente de reprise",
    upload_sent: "Téléversement envoyé ; en attente du serveur",
  },
}
